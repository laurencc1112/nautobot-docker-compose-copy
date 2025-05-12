# Explanation of job functions:
# The purpose of this job is to change a batch of interfaces to a wireless configuration.
# This job: allows the user to select a device location, select multiple devices (switches) from that location, select multiple
#   interfaces from those switches, and select an applicable wireless vlan, or defaults to the vlan 300 for the selected location.
#   After the selections are made, it checks to ensure that none of the selected interfaces are set to 'tagged' mode. If they are
#   set to tagged, job immediately fails. Otherwise, it sets the interface status to 'active', sets enabled to 'true', sets the
#   mode to 'access' if not already set, sets the untagged vlan to either the user selected vlan or VID=300 for the location,
#   removes all tags except 'STP:portfast' or adds that tag if it is missing.
# This job utilizes a computed field to display the switch name - interface name for the user.
# - LC

from nautobot.apps.jobs import Job, MultiObjectVar, ObjectVar
from nautobot.dcim.models import Device, Interface, Location, LocationType
from nautobot.extras.models import Tag, Status
from nautobot.ipam.models import VLAN
from nautobot.apps.jobs import register_jobs


class ModifyInterfacesToWirelessConfig(Job):
    """Enables interface, sets only STP:portfast tag, and changes vlan to user selected or vlan 300 for site."""

    class Meta:
        name = "Modify Interfaces to Wireless Configuration"
        description = "Enables interface, sets only STP:portfast tag, and changes vlan to user selected or vlan 300 for site.."
        approval_required = True

    location = ObjectVar(
        label="Location",
        model=Location,
        required=True,
        description="Select a building location (not room, MDFs, or IDFs).",
    )

    devices = MultiObjectVar(
        model=Device,
        query_params={"location": "$location"},  ### Only show devices from the selected location
        description="Select devices to modify interfaces on. Only devices from the selected location will be shown.",
        required=True,
    )

    interfaces = MultiObjectVar(
        label="Interfaces",
        model=Interface,
        display_field="computed_fields.device_interface",  ### Ensures device - interface is shown
        query_params={
            "device": "$devices",  ### Only show interfaces from selected devices
            "include": "computed_fields",  ### Ensures computed fields are included in API response
        },
        description="Select interfaces to modify (filtered by selected devices).",
        required=True,
    )

    vlan_choice = ObjectVar(
        model=VLAN,
        query_params={"location": "$location"},  ### Only show vlans from the selected location
        description="Select a VLAN from the same location as the device. Defaults to VLAN 300 if none selected.",
        required=False,
    )

    def run(self, location, devices, interfaces, vlan_choice):
        """Perform tag removal on the selected interfaces and update VLANs."""


        ### Make sure selected location is a building for vlan ineritance
        building_type = LocationType.objects.filter(name__iexact="building").first()
        if not building_type or location.location_type != building_type:
            raise Exception(
                f"The selected location '{location.name}' is not of type 'Building'. "
                "Please select a top-level building (not a closet or MDF)."
            )

        ### Fail immediately if any trunk (tagged/tagged-all) ports are selected
        trunk_ports = [
            f"{iface.device.name} - {iface.name}"
            for iface in interfaces
            if iface.mode in ["tagged", "tagged-all"] or iface.lag is not None
        ]

        if trunk_ports:
            self.logger.error(
                "You have selected a trunk port to be modified. You must either select only access ports "
                "or change these ports to access manually before continuing. Cancelling job."
            )
            for port in trunk_ports:
                self.logger.error(f"Trunk port: {port}")
            raise Exception(
                "You have selected a trunk port to be modified. You must either select only access ports or change this port to access manually before continuing. Cancelling job."
            )

        ### Get the VLAN choice or default to VLAN 300
        selected_vlan = vlan_choice or VLAN.objects.filter(vid=300, location=location).first()

        if not selected_vlan:
            self.logger.error(f"VLAN 300 does not exist at location {location}. Job failed.")
            raise Exception(f"VLAN 300 not found at location {location}.")

        ### Get the STP:portfast tag
        stp_portfast_tag = Tag.objects.filter(name="STP:portfast").first()
        if not stp_portfast_tag:
            self.logger.warning("The tag 'STP:portfast' does not exist in Nautobot.")

        ### Get the 'Active' status object
        active_status = Status.objects.get(name="Active")

        ### Log selected devices and interfaces
        self.logger.info(f"Selected location: {location}")
        for device in devices:
            self.logger.info(f"- {device.name}")

        self.logger.info("Selected Interfaces:")
        for interface in interfaces:
            self.logger.info(f"- {interface.device.name} - {interface.name}")

        modified_interfaces = []

        for interface in interfaces:
            current_tags = set(interface.tags.all())

            ### Keep only STP:portfast, remove everything else
            new_tags = {tag for tag in current_tags if tag.name == "STP:portfast"}

            ### Add STP:portfast tag if missing
            if stp_portfast_tag and stp_portfast_tag not in new_tags:
                new_tags.add(stp_portfast_tag)

            ### Update status and enabled fields
            interface.status = active_status
            interface.enabled = True

            ### Ensure mode is set before assigning untagged VLAN
            if not interface.mode:
                interface.mode = "access"

            ### Update interface with tags and vlan
            interface.tags.set(new_tags)
            interface.untagged_vlan = selected_vlan
            interface.validated_save()

            modified_interfaces.append(
                f"{interface.device.name} - {interface.name} (Status: Active, Enabled: True, Mode: {interface.mode}, Tags: {', '.join(tag.name for tag in new_tags)}, VLAN: {selected_vlan.vid})"
            )
            self.logger.info(
                f"Updated {interface.device.name} - {interface.name}: set status='Active', enabled=True, mode='access' (if unset), kept only 'STP:portfast', set VLAN {selected_vlan.vid}."
            )

        if modified_interfaces:
            return f"Modified {len(modified_interfaces)} interfaces at {location}:\n" + "\n".join(modified_interfaces)
        else:
            return "No changes were needed."


register_jobs(ModifyInterfacesToWirelessConfig)

