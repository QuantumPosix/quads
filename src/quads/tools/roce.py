import argparse
import logging
import sys
from collections import defaultdict

from quads.config import Config
from quads.quads_api import QuadsApi
from quads.tools.external.juniper_roce import JuniperRoCE, JuniperRoCEException

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.propagate = False
logging.basicConfig(level=logging.INFO, format="%(message)s")

quads = QuadsApi(Config)


class RoCEConfigurator:
    def __init__(self, hostname, action, interfaces=None, dry_run=False):
        self.hostname = hostname
        self.action = action
        self.interfaces = interfaces
        self.dry_run = dry_run

    def _get_host(self):
        host = quads.get_host(self.hostname)
        if not host:
            logger.error("Host not found: %s", self.hostname)
            return None
        if not host.interfaces:
            logger.error("Host %s has no interfaces defined", self.hostname)
            return None
        return host

    def _get_switch_map(self, host):
        switch_map = defaultdict(list)
        for interface in host.interfaces:
            switch_map[interface.switch_ip].append(interface)
        return switch_map

    def _get_filtered_switch_map(self, host):
        available = {iface.name for iface in host.interfaces}
        requested = set(self.interfaces)
        missing = requested - available
        if missing:
            logger.error(
                "Interfaces not found on host %s: %s",
                self.hostname,
                ", ".join(sorted(missing)),
            )
            return None

        switch_map = defaultdict(list)
        for interface in host.interfaces:
            if interface.name in requested:
                switch_map[interface.switch_ip].append(interface)
        return switch_map

    def run(self):
        dispatch = {
            "install_roce": self.install_roce,
            "uninstall_roce": self.uninstall_roce,
            "configure": self.configure,
            "remove": self.remove,
        }
        return dispatch[self.action]()

    def install_roce(self):
        host = self._get_host()
        if host is None:
            return False

        switch_map = self._get_switch_map(host)
        logger.info(
            "Installing base RoCE config for host %s: %d switch(es)",
            self.hostname,
            len(switch_map),
        )

        all_success = True
        for switch_ip in switch_map:
            if self.dry_run:
                logger.info(
                    "[DRY RUN] Would install base RoCE config on switch: %s",
                    switch_ip,
                )
                continue

            try:
                juniper = JuniperRoCE(switch_ip)
                juniper.connect()
            except JuniperRoCEException:
                logger.error("Failed to connect to switch: %s", switch_ip)
                all_success = False
                continue

            if juniper.has_base_config():
                logger.info(
                    "Base RoCE config already present on switch: %s, skipping",
                    switch_ip,
                )
                juniper.close()
                continue

            if juniper.apply_base_config():
                logger.info("Installed base RoCE config on switch: %s", switch_ip)
            else:
                logger.error("Failed to install base config on switch: %s", switch_ip)
                all_success = False

            juniper.close()

        return all_success

    def uninstall_roce(self):
        host = self._get_host()
        if host is None:
            return False

        switch_map = self._get_switch_map(host)
        logger.info(
            "Uninstalling base RoCE config for host %s: %d switch(es)",
            self.hostname,
            len(switch_map),
        )

        all_success = True
        for switch_ip in switch_map:
            if self.dry_run:
                logger.info(
                    "[DRY RUN] Would uninstall base RoCE config from switch: %s",
                    switch_ip,
                )
                continue

            try:
                juniper = JuniperRoCE(switch_ip)
                juniper.connect()
            except JuniperRoCEException:
                logger.error("Failed to connect to switch: %s", switch_ip)
                all_success = False
                continue

            if not juniper.has_base_config():
                logger.info("No base RoCE config found on switch: %s, skipping", switch_ip)
                juniper.close()
                continue

            if juniper.remove_base_config():
                logger.info("Uninstalled base RoCE config from switch: %s", switch_ip)
            else:
                logger.error("Failed to uninstall base config from switch: %s", switch_ip)
                all_success = False

            juniper.close()

        return all_success

    def configure(self):
        host = self._get_host()
        if host is None:
            return False

        switch_map = self._get_filtered_switch_map(host)
        if switch_map is None:
            return False

        logger.info(
            "Configuring RoCE interfaces for host %s: %d switch(es)",
            self.hostname,
            len(switch_map),
        )

        all_success = True
        for switch_ip, interfaces in switch_map.items():
            if self.dry_run:
                logger.info(
                    "[DRY RUN] Would configure interfaces on switch: %s",
                    switch_ip,
                )
                for iface in interfaces:
                    logger.info(
                        "[DRY RUN] Would apply interface config for: %s",
                        iface.switch_port,
                    )
                continue

            try:
                juniper = JuniperRoCE(switch_ip)
                juniper.connect()
            except JuniperRoCEException:
                logger.error("Failed to connect to switch: %s", switch_ip)
                all_success = False
                continue

            if not juniper.has_base_config():
                logger.error(
                    "Base RoCE config not found on switch: %s. " "Run --install-roce first.",
                    switch_ip,
                )
                juniper.close()
                all_success = False
                continue

            for iface in interfaces:
                if juniper.apply_interface_config(iface.switch_port):
                    logger.info(
                        "Applied RoCE interface config for %s on %s",
                        iface.switch_port,
                        switch_ip,
                    )
                else:
                    logger.error(
                        "Failed to apply interface config for %s on %s",
                        iface.switch_port,
                        switch_ip,
                    )
                    all_success = False

            juniper.close()

        return all_success

    def remove(self):
        host = self._get_host()
        if host is None:
            return False

        switch_map = self._get_filtered_switch_map(host)
        if switch_map is None:
            return False

        logger.info(
            "Removing RoCE interface configs for host %s: %d switch(es)",
            self.hostname,
            len(switch_map),
        )

        all_success = True
        for switch_ip, interfaces in switch_map.items():
            if self.dry_run:
                logger.info(
                    "[DRY RUN] Would remove interface configs on switch: %s",
                    switch_ip,
                )
                for iface in interfaces:
                    logger.info(
                        "[DRY RUN] Would remove interface config for: %s",
                        iface.switch_port,
                    )
                continue

            try:
                juniper = JuniperRoCE(switch_ip)
                juniper.connect()
            except JuniperRoCEException:
                logger.error("Failed to connect to switch: %s", switch_ip)
                all_success = False
                continue

            for iface in interfaces:
                if juniper.remove_interface_config(iface.switch_port):
                    logger.info(
                        "Removed RoCE interface config for %s on %s",
                        iface.switch_port,
                        switch_ip,
                    )
                else:
                    logger.error(
                        "Failed to remove interface config for %s on %s",
                        iface.switch_port,
                        switch_ip,
                    )
                    all_success = False

            juniper.close()

        return all_success


def main():  # pragma: no cover
    parser = argparse.ArgumentParser(description="Manage RoCE configuration on switches for a QUADS host")
    parser.add_argument("--host", required=True, help="Hostname (e.g., host01.example.com)")
    parser.add_argument(
        "--interfaces",
        type=str,
        default=None,
        help="Comma-separated interface names (e.g., em1,em3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without applying changes",
    )

    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--install-roce",
        dest="action",
        action="store_const",
        const="install_roce",
        help="Install base RoCE config to switches",
    )
    actions.add_argument(
        "--uninstall-roce",
        dest="action",
        action="store_const",
        const="uninstall_roce",
        help="Remove base RoCE config from switches",
    )
    actions.add_argument(
        "--configure",
        dest="action",
        action="store_const",
        const="configure",
        help="Apply per-interface RoCE config (requires base already installed)",
    )
    actions.add_argument(
        "--remove",
        dest="action",
        action="store_const",
        const="remove",
        help="Remove per-interface RoCE config (leaves base config intact)",
    )

    args = parser.parse_args()

    if args.action in ("configure", "remove") and not args.interfaces:
        parser.error(f"--interfaces is required for --{args.action.replace('_', '-')}")

    iface_list = None
    if args.interfaces:
        iface_list = [i.strip() for i in args.interfaces.split(",")]

    configurator = RoCEConfigurator(args.host, args.action, interfaces=iface_list, dry_run=args.dry_run)
    success = configurator.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
