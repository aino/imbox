from __future__ import unicode_literals

import email
import time
from datetime import datetime
from email.header import decode_header
from imbox.utils import str_encode, str_decode
from six import StringIO


class Struct(object):
    def __init__(self, **entries):
        self.__dict__.update(entries)

    def keys(self):
        return self.__dict__.keys()

    def __repr__(self):
        return str(self.__dict__)


def decode_mail_header(value, default_charset='us-ascii'):
    """
    Decode a header value into a unicode string.
    """
    try:
        headers = decode_header(value)
    except email.errors.HeaderParseError:
        return str_decode(str_encode(value, default_charset, 'replace'), default_charset)
    else:
        for index, (text, charset) in enumerate(headers):
            try:
                headers[index] = str_decode(text, charset or default_charset, 'replace')
            except LookupError:
                # if the charset is unknown, force default
                headers[index] = str_decode(text, default_charset, 'replace')
        return ''.join(headers)


def get_mail_addresses(message, header_name):
    """
    Retrieve all email addresses from one message header.
    """
    headers = [h for h in message.get_all(header_name, [])]
    addresses = email.utils.getaddresses(headers)
    for index, (address_name, address_email) in enumerate(addresses):
        addresses[index] = {
            'name': decode_mail_header(address_name),
            'email': address_email
        }
    return addresses


def parse_attachment(message_part):
    content_disposition = message_part.get("Content-Disposition")
    if content_disposition:
        dispositions = content_disposition.strip().split(";")
        if dispositions[0].lower() in ["attachment", "inline"]:
            data = message_part.get_payload(decode=True)
            attachment = {
                'content-type': message_part.get_content_type(),
                'size': len(data),
                'content': StringIO(data)
            }
            for param in dispositions[1:]:
                key, value = param.split('=', 1)
                key = key.lower().strip()
                value = value.strip('"')
                attachment[key] = value
            return attachment


def parse_email(raw_email):
    email_message = email.message_from_string(raw_email)
    maintype = email_message.get_content_maintype()
    parsed_email = {}
    parsed_email['raw_email'] = raw_email
    body = {
        "plain": [],
        "html": []
    }
    attachments = []
    if maintype == 'multipart':
        for part in email_message.walk():
            content = part.get_payload(decode=True)
            content_type = part.get_content_type()
            content_disposition = part.get('Content-Disposition', None)
            is_inline = content_disposition is None \
                or content_disposition == "inline"
            if content_type == "text/plain" and is_inline:
                body['plain'].append(content)
            elif content_type == "text/html" and is_inline:
                body['html'].append(content)
            elif content_disposition:
                attachment = parse_attachment(part)
                if attachment:
                    attachments.append(attachment)
    elif maintype == 'text':
        payload = email_message.get_payload(decode=True)
        body['plain'].append(payload)
    parsed_email['attachments'] = attachments
    parsed_email['body'] = body
    email_dict = dict(email_message.items())
    parsed_email['sent_from'] = get_mail_addresses(email_message, 'from')
    parsed_email['sent_to'] = get_mail_addresses(email_message, 'to')
    value_headers_keys = ['subject', 'date', 'message-id']
    key_value_header_keys = [
        'received-spf',
        'mime-version',
        'x-spam-status',
        'x-spam-score',
        'content-type'
    ]
    parsed_email['headers'] = []
    for key, value in email_dict.items():
        if key.lower() in value_headers_keys:
            valid_key_name = key.lower().replace('-', '_')
            parsed_email[valid_key_name] = decode_mail_header(value)
        if key.lower() in key_value_header_keys:
            parsed_email['headers'].append({'Name': key, 'Value': value})
    if parsed_email.get('date'):
        timetuple = email.utils.parsedate(parsed_email['date'])
        parsed_date = datetime.fromtimestamp(time.mktime(timetuple)) \
            if timetuple else None
        parsed_email['parsed_date'] = parsed_date
    return Struct(**parsed_email)
