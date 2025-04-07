from nautobot.apps.jobs import Job, MultiObjectVar, ObjectVar
from nautobot.dcim.models import Device, Interface, Location
from nautobot.extras.models import Tag
from nautobot.ipam.models import VLAN
from nautobot.apps.jobs import register_jobs


class ModifyInterfacesToWirelessConfig(Job):
    """Removes all tags from selected interfaces except STP:portfast and sets untagged vlan to a user selected vlan (default 300)."""

    class Meta:
        name = "Modify Interfaces to Wireless Configuration"
        description = "Removes all tags from selected interfaces except STP:portfast and sets untagged vlan to a selected vlan."
        approval_required = True

    location = ObjectVar(
        label="Location",
        model=Location,
        required=True,
        description="Select the location for the devices.",
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

        ### Get the VLAN choice or default to VLAN 300
        selected_vlan = vlan_choice or VLAN.objects.filter(vid=300, location=location).first()

        if not selected_vlan:
            self.logger.error(f"VLAN 300 does not exist at location {location}. Job aborted.")
            raise Exception(f"VLAN 300 not found at location {location}. Ensure it exists in Nautobot.")

        ### Get the STP:portfast tag
        stp_portfast_tag = Tag.objects.filter(name="STP:portfast").first()
        if not stp_portfast_tag:
            self.logger.warning("The tag 'STP:portfast' does not exist in Nautobot.")

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
            if stp_portfast_tag and "STP:portfast" not in {tag.name for tag in new_tags}:
                new_tags.add(stp_portfast_tag)

            ### Update interface with tags and vlan
            interface.tags.set(new_tags)
            interface.untagged_vlan = selected_vlan
            interface.validated_save()

            modified_interfaces.append(
                f"{interface.device.name} - {interface.name} (Tags: {', '.join(tag.name for tag in new_tags)}, VLAN: {selected_vlan.vid})"
            )
            self.logger.info(
                f"Updated {interface.device.name} - {interface.name}, keeping only 'STP:portfast' and setting VLAN {selected_vlan.vid}."
            )

        if modified_interfaces:
            return f"Modified {len(modified_interfaces)} interfaces at {location}: \n" + "\n".join(modified_interfaces)
        else:
            return "No changes were needed."


register_jobs(ModifyInterfacesToWirelessConfig)
