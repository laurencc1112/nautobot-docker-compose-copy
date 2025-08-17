# jobs/ping_gateways.py

"""
Ping vlan gateways for a selected building.

Requirements:
- ping3 must be installed in the environment.

Author: Lauren Crow
Date: 6/18/25
Last Modified By:
Last Modified Date:
"""

from nautobot.apps.jobs import Job, ObjectVar
from nautobot.dcim.models import Location
from nautobot.ipam.models import VLANGroup, VLAN, Prefix
import ipaddress
import ping3
from nautobot.apps.jobs import register_jobs


class PingGatewaysJob(Job):
    """Ping vlan gateways for a selected building using ICMP and summarize the results.

    This job retrieves all vlans associated with a selected building via their vlan group,
    finds the first usable IP (assumed gateway) for each prefix assigned to those vlans,
    and uses ping3 to test reachability. A summary is printed at the end, organized
    by successful and failed pings. The average of 5 pings is shown to the user.

    """

    class Meta:
        name = "Ping Vlan Gateways"
        description = "Ping vlan gateways for a selected building."
        field_order = ["building"]

    building = ObjectVar(
        model=Location,
        query_params={"location_type": "Building"},
        label="Select a building to test.",
        required=True,
    )

    def run(self, building, **kwargs):
        """Execute the job logic.

        Args:
            building (Location): The building Location object selected by the user.

        Retrieves:
            - All vlan groups assigned to the building
            - All vlanss in those groups
            - All prefixes assigned to each vlan

        Behavior:
            - Pings the first usable IP in each prefix (assumed to be the gateway)
            - Logs average round-trip time (RTT) over 5 pings
            - Logs success or failure for each gateway
            - At the end, prints a summary grouped by successes and failures
        """
        self.logger.info(f"Selected building: {building.name}")

        summary = []

        vlan_groups = VLANGroup.objects.filter(location=building)
        if not vlan_groups.exists():
            self.logger.error(f"No Vlan Groups found for building {building.name}.")
            return

        for vlan_group in vlan_groups:
            self.logger.info(f"Found Vlan Group: {vlan_group.name}")

            vlans = VLAN.objects.filter(vlan_group=vlan_group)
            if not vlans.exists():
                self.logger.warning(f"No Vlans found in group {vlan_group.name}.")
                continue

            for vlan in vlans:
                vlan_id = vlan.vid
                vlan_name = vlan.name or "(no name)"

                prefixes = vlan.prefixes.all()
                if not prefixes:
                    self.logger.warning(f"Vlan {vlan_id} ({vlan_name}): No prefixes assigned — skipping.")
                    continue

                for prefix in prefixes:
                    try:
                        net = ipaddress.ip_network(prefix.prefix)
                        gateway_ip = str(list(net.hosts())[0])  # First usable host IP

                        self.logger.info(f"Vlan {vlan_id} ({vlan_name}) — Testing gateway {gateway_ip}...")

                        # Send 5 pings and calculate average RTT
                        rtts = []
                        for _ in range(5):
                            rtt = ping3.ping(gateway_ip, timeout=2, unit="ms")
                            if rtt is not None:
                                rtts.append(rtt)

                        if rtts:
                            avg_rtt = sum(rtts) / len(rtts)
                            self.logger.info(
                                f"VLAN {vlan_id} ({vlan_name}) — Gateway {gateway_ip} reachable, avg RTT={avg_rtt:.2f} ms"
                            )
                            summary.append({
                                "vlan": vlan_id,
                                "gateway": gateway_ip,
                                "result": "Success",
                            })
                        else:
                            self.logger.error(
                                f"VLAN {vlan_id} ({vlan_name}) — Gateway {gateway_ip} unreachable"
                            )
                            summary.append({
                                "vlan": vlan_id,
                                "gateway": gateway_ip,
                                "result": "Failure",
                            })

                    except Exception as e:
                        self.logger.error(
                            f"VLAN {vlan_id} ({vlan_name}) — Error testing prefix {prefix.prefix}: {str(e)}"
                        )
                        summary.append({
                            "vlan": vlan_id,
                            "gateway": prefix.prefix,
                            "result": "Failure",
                        })

        self.logger.info("Ping test completed.\n")
        self.logger.info("========= Gateway Ping Summary =========")

        successes = [item for item in summary if item["result"] == "Success"]
        failures = [item for item in summary if item["result"] != "Success"]

        if successes:
            self.logger.info("========= Successful Pings =========")
            for item in successes:
                self.logger.info(f"VLAN {item['vlan']} — Gateway {item['gateway']} — Success")

        if failures:
            self.logger.info("========= Failed Pings =========")
            for item in failures:
                self.logger.info(f"VLAN {item['vlan']} — Gateway {item['gateway']} — Failure")


register_jobs(PingGatewaysJob)
