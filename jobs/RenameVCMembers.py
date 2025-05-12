# This job will allow the user to select an existing virtual chassis to rename.
# After selecting the virtual chassis, they will enter in a new name in a text field.
# The job will then rename the virtual chassis to the new name, then go through and
# rename all members to the new name, keeping the .1-4 suffix for each device.

import re
from nautobot.core.jobs import Job, ObjectVar, StringVar, register_jobs
from nautobot.dcim.models import VirtualChassis, Device
from nautobot.extras.jobs import ValidationError

class RenameVCMembers(Job):
    class Meta:
        name = "Rename Virtual Chassis and Members"
        description = "Select a virtual chassis and list its member devices."

    # Drop-down selet for Virtual Chassis
    virtual_chassis = ObjectVar(
        model=VirtualChassis,
        required=True,
        label="Select Virtual Chassis"
    )

    # Text box for inputing new name
    new_name = StringVar(
        description="New name for the virtual chassis stack.",
        required=True
    )

    def run(self, virtual_chassis, new_name):
        # Validate structure of new name
        pattern = r"^\d{4}-[a-z0-9]{3,6}-[a-z0-9]+-\d[k]-[a-z0-9]{1,3}$"
        if not re.match(pattern, new_name):
            raise ValidationError({"new_name": "Invalid name. Must match bldg-abbr-rm#-#k-r (e.g., 0123-engr-105-1k-as1)."})

        # Get the VC and Members
        vc = virtual_chassis
        members = Device.objects.filter(virtual_chassis=vc).order_by("vc_position")

        # Log virtual chassis name change
        self.logger.info(f"Renaming Virtual chassic '{vc.name}' to '{new_name}'")

        # Set the new name and save changes
        vc.name = new_name
        vc.save()

        for member in members:
            # Split member name at the dot keep the suffix
            suffix = member.name.split('.', 1)[1]
            # Add suffix to new name
            new_member_name = f"{new_name}.{suffix}"

            # Log member name changes
            self.logger.info(f"Renaming device '{member.name}' to '{new_member_name}'")

            # Set the new name and save changes.
            member.name = new_member_name
            member.save()

        return "Virtual Chassis and Members renamed Successfully"
register_jobs(RenameVCMembers)
