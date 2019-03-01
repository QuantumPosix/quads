#! /usr/bin/env/ python3
import logging
import smtplib

from email.message import EmailMessage
from email.headerregistry import Address
from quads.config import conf

logger = logging.getLogger(__name__)


class Postman(object):
    def __init__(self, subject, to, cc, content):
        self.subject = subject
        self.to = to
        self.cc = cc
        self.content = content

    def send_email(self):
        msg = EmailMessage()
        msg["Subject"] = self.subject
        msg["From"] = Address("QUADS", "quads", conf["domain"])
        msg["To"] = Address(username=self.to, domain=conf["domain"])
        msg["Cc"] = ",".join(self.cc)
        msg.add_header("Reply-To", "dev-null@%s" % conf["domain"])
        msg.attach(self.content)
        emailhost = conf["email_host"]
        with smtplib.SMTP(emailhost) as s:
            try:
                logger.debug(msg)
                s.send_message(msg)
            except smtplib.SMTPException as ex:
                logger.debug(ex)
                logger.error("Postman got bit by a dog, woof! woof!")
                return False
        return True