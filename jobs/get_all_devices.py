from nautobot.apps.jobs import Job, register_jobs
from nautobot.dcim.models import Device

class GetAllDevices(Job):
    """Retrieve a list of all devices in Nautobot."""

    class Meta:
        name = "Get All Devices"
        description = "This job retrieves all devices from Nautobot and posts the results."
        read_only = True

    def run(self):
        """Execute the job to fetch all devices."""
        devices = Device.objects.all()

        if not devices:
            self.logger.warning("No devices found in Nautobot.")
            return "No devices found."

        device_details = [f"- {device.name} ({device.status})" for device in devices]

        for device in device_details:
            self.logger.info(device)

        return f"Retrieved {len(devices)} devices:\n" + "\n".join(device_details)

register_jobs(GetAllDevices)

