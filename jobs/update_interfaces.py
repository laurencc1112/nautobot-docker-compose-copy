from nautobot.apps.jobs import Job, MultiObjectVar, ObjectVar
from nautobot.dcim.models import Device, Interface, Location
from nautobot.ipam.models import VLAN
from nautobot.extras.models import Status
from nautobot.apps.jobs import register_jobs

class UpdateInterfacesToAccessVLAN300(Job):
    """Change specified interfaces on devices to mode access and VLAN 300."""

    class Meta:
        name = "Update Interfaces to Access VLAN 300"
        description = "This job updates selected interfaces to mode access and assigns VLAN 300."
        approval_required = True

    devices = MultiObjectVar(
        model=Device,
        description="Select devices to modify interfaces on. Devices must be from the same location.",
        required=True,
    )

    interfaces = MultiObjectVar(
        model=Interface,
        query_params={"device_id": "$devices"},
        description="Select interfaces to modify (filtered by the selected devices).",
        required=True,
    )

    def run(self, devices, interfaces):
        """Perform the interface update."""

        ### make sure all selected devices are from the same location
        locations = {device.location for device in devices}
        if len(locations) > 1:
            self.logger.error(f"Selected devices are from multiple locations: {locations}. Job aborted.")
            raise Exception(f"Devices must be from the same location. Selected locations: {locations}")

        ### get the common location
        location = locations.pop()

        ### retrieve VLAN 300 with proper location filtering
        vlan_300 = VLAN.objects.filter(vid=300, location__in=location.get_ancestors(include_self=True)).first()

        if not vlan_300:
            self.logger.error(f"VLAN 300 does not exist at location {location}. Job aborted.")
            raise Exception(f"VLAN 300 not found at location {location}. Ensure it exists in Nautobot.")

        self.logger.info(f"All selected devices are from: {location}")
        for device in devices:
            self.logger.info(f"- {device.name}")

        self.logger.info("Selected Interfaces:")
        for interface in interfaces:
            self.logger.info(f"- {interface.name} on {interface.device.name}")

        ### update each interface
        for interface in interfaces:
            interface.mode = "access"  
            interface.untagged_vlan = vlan_300
            interface.validated_save()
            self.logger.info(
                f"Updated {interface.name} on {interface.device.name} to mode access with VLAN 300."
            )

        return f"Successfully updated {len(interfaces)} interfaces to mode access and VLAN 300."

register_jobs(UpdateInterfacesToAccessVLAN300)
