# jobs/create_vlan.py

"""
Create a vlan object and interface on a router.

This job::
1. Prompts the user for a router, vlan num, vlan name, and subnet.
2. Identifys the building location by getting the ancestor location of the selected router.
3. Retrieves the vlan group that exists at the building level location.
4. Creates a new vlan object with the given ID and name, associated with the VLAN group and building location.
5. Creates a new IPAM prefix with the provided subnet and associate it with the new vlan.
6. Determines the gateway IP address as the first usable IP in the subnet.
7. Creates an IPAddress object using the gateway IP and subnet mask.
8. Creates a vlan interface on the selected router with the name "Vlan<ID>" and type "virtual".
9. Assigns the gateway IP address to the new vlan interface.
10. If the vlan name contains 'voice' or 'voip', add the VOICE role to the vlan.

Author: Lauren Crow
Date: 7/5/25
Last Modified By:
Last Modified Date:
"""

from nautobot.extras.jobs import Job, ObjectVar, StringVar, IPAddressVar
from nautobot.dcim.models import Device, Interface
from nautobot.ipam.models import VLAN, VLANGroup, Prefix, IPAddress
from nautobot.extras.models import Status, Role, Tag
from nautobot.dcim.models.locations import Location
from nautobot.apps.jobs import Job, register_jobs
from django.contrib.contenttypes.models import ContentType
import ipaddress

class CreateVLAN(Job):
    """Create a vlan on a router and in IPAM."""

    class Meta:
        name = "Create Vlan"
        description = "This job allows you to create a new vlan on a router."

    router = ObjectVar(
        model=Device,
        description="Select the router where the vlan should be created."
    )

    vlan_id = StringVar(
        description="Vlan number"
    )

    vlan_name = StringVar(
        description="Vlan name"
    )

    subnet = StringVar(
        description="Subnet ID in CIDR Notation (ex 1.1.1.0/24)"
    )

    helper_address = ObjectVar(
        model=Tag,
        query_params={
            "name__ic": "helper"
        },
        required=False,
        description="Optional Helper Addresses"
    )

    def run(self, router, vlan_id, vlan_name, subnet, helper_address):
        self.logger.info(f"Creating vlan {vlan_id} ({vlan_name}) on {router.name} with subnet {subnet}")

        ### Get building location from router's location
        building_location = router.location.ancestors().last()
        if not building_location:
            self.logger.error(f"Unable to determine building location for router {router.name}")
            return

        ### Find the vlan group assigned to the same building location
        vlan_group = VLANGroup.objects.filter(location=building_location).first()
        if not vlan_group:
            self.logger.error(f"No vlangroup found at location {building_location.name}")
            return

        status = Status.objects.get(name="Active")
    
        network = ipaddress.ip_network(subnet, strict=False)

        ### Create the vlan
        vlan = VLAN.objects.create(
            vid=vlan_id,
            name=vlan_name,
            vlan_group=vlan_group,
            location=building_location,
            status=status
        )
        self.logger.info(f"Created vlan {vlan.vid} in group {vlan_group.name}")

        ### Assign VOICE tag if vlan name contains 'voice' or 'voip'
        if "voice" in vlan_name.lower() or "voip" in vlan_name.lower():
            try:
                voice_role = Role.objects.get(name="VOICE")
                vlan.role = voice_role
                vlan.save()
                self.logger.info(f"Applied VOICE role to VLAN {vlan.name}")
            except Role.DoesNotExist:
                self.logger.warning('VOICE role does not exist — skipping role assignment.')    

        ### Create the prefix
        prefix = Prefix.objects.create(
            prefix=subnet,
            vlan=vlan,
            status=status
        )
        self.logger.info(f"Created prefix {prefix.prefix} and associated it with vlan {vlan.vid}")

        ### Determine gateway IP as second address
        gateway_ip = f"{list(network.hosts())[0]}/{network.prefixlen}"

        ### Create the IP address object
        ip_address = IPAddress.objects.create(
            address=gateway_ip,
            status=status
        )
        self.logger.info(f"Created gateway IP address {ip_address.address}")

        ### Create the vlan interface
        interface_name = f"Vlan{vlan_id}"
        interface, _ = Interface.objects.get_or_create(
            device=router,
            name=interface_name,
            type="virtual",
            description=vlan_name,
            defaults={"status": status}
        )

        ### Set helper address tags if applicable
        if helper_address:
            interface.tags.set([helper_address])
            self.logger.info(f"Applied helper tag {helper_address.name} to interface {interface.name}")
    
        ### Enable the interface
        interface.enabled = True
        interface.save()
        
        ### Assign IP to vlan interface
        interface.ip_addresses.add(ip_address)

        self.logger.info(f"Assigned {ip_address.address} to interface {interface.name} on {router.name}")

        return f"Created vlan {vlan.vid}, prefix {prefix.prefix}, and assigned gateway {ip_address.address} to interface {interface.name} on {router.name}."

register_jobs(CreateVLAN)
