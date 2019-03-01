#!/usr/bin/env python
import logging

from paramiko import SSHClient, AutoAddPolicy

logger = logging.getLogger(__name__)


class SSHHelper(object):
    def __init__(self, _host, _user=None, _password=None):
        self.host = _host
        self.user = _user
        self.password = _password
        self.ssh = self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        ssh = SSHClient()
        ssh.set_missing_host_key_policy(AutoAddPolicy())
        ssh.load_system_host_keys()

        ssh.connect(
            self.host,
            username=self.user,
            password=self.password,
            allow_agent=False,
        )
        transport = ssh.get_transport()
        channel = transport.open_session()
        channel.setblocking(1)
        return ssh

    def disconnect(self):
        self.ssh.close()

    def run_cmd(self, cmd):
        stdin, stdout, stderr = self.ssh.exec_command(cmd)

        if stderr.readlines():
            logger.error("There was something wrong with your request")
            for line in stderr.readlines():
                logger.error(line)
            return False
        else:
            logger.info("Your command was executed successfully")
            return stdout.readlines()

    def copy_ssh_key(self, _ssh_key):

        with open(_ssh_key, "r") as _file:
            key = _file.readline().strip()

        command = 'echo "%s" >> ~/.ssh/authorized_keys' % key
        stdin, stdout, stderr = self.ssh.exec_command(command)

        if stderr.readlines():
            logger.error("There was something wrong with your request")
            for line in stderr.readlines():
                logger.error(line)
        else:
            logger.info("Your key was copied successfully")