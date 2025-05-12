from nautobot.apps.jobs import Job, MultiObjectVar, ObjectVar, ChoiceVar
from nautobot.dcim.models import Device, Interface, Location, LocationType
from nautobot.extras.models import Tag, Status
from nautobot.ipam.models import VLAN
from nautobot.apps.jobs import register_jobs


class ModifyInterfaceConfigurations(Job):
    """
    Configure selected interfaces to match a specific configuration type.

    This job enables batch modification of interface attributes on selected devices within a specified building.
    Users can choose from predefined configuration types such as "wireless", "voice", "user", etc., each of which
    applies a standardized set of "configurations" such as an untagged vlan, tags, and interface descriptions. It 
    will also ensure the interface is enabled, status set to active, and in access mode.

    The job provides dropdowns to select:
      - A valid building location (only buildings, not closets or IDFs)
      - Devices from that location
      - Interfaces from the selected devices
      - An optional VLAN (defaulting to a config-specific fallback)
      - A configuration type that determines the settings applied

    Arguments:
        config_type (`str`): The selected configuration type (e.g., 'wireless', 'voice', etc).
        location (`Location`): The building location to operate within.
        devices (`List[Device]`): Devices located within the selected building.
        interfaces (`List[Interface]`): Interfaces from the selected devices to configure.
        vlan_choice (`VLAN`, optional): A specific VLAN to assign as untagged VLAN. Defaults to a fallback.

    Returns:
        `str`: A summary of the interfaces modified, or a message indicating no changes were made.

    Raises:
        Exception: If trunk/LAG interfaces are selected, if the location isn't a building, or required VLANs/tags are missing.
    """

    class Meta:
        name = "Configure Interfaces by Type"
        description = "Configure selected interfaces based on a chosen configuration type."
        approval_required = True

    CONFIG_TYPE_CHOICES = [
        ("user", "User"),
        ("voice", "Voice"),
        ("wireless", "Wireless"),
        ("building_services", "Building Services"),
        ("ues", "UES"),
        ("camera", "Camera"),
        ("other", "Other"),
    ]

    CONFIG_DEFAULT_VLANS = {
        "user": 100,
        "voice": 200,
        "wireless": 300,
        "building_services": 500,
        "ues": 600,
        "camera": 700,
    }

    CONFIG_REQUIRED_TAGS = {
        "user": ["Port:VOIP", "STORMCONTROL:1.5", "STP:portfast"],
        "voice": ["STP:portfast"],
        "wireless": ["STP:portfast"],
        "building_services": ["STP:portfast"],
        "ues": ["STP:portfast"],
        "camera": ["STP:portfast"],
    }

    config_type = ChoiceVar(
        choices=CONFIG_TYPE_CHOICES,
        required=True,
        label="Interface Configuration Type",
        description="Select the configuration type to apply to the selected interfaces.",
    )

    location = ObjectVar(
        label="Location",
        model=Location,
        required=True,
        description="Select a building location (not room, MDFs, or IDFs).",
    )

    devices = MultiObjectVar(
        model=Device,
        query_params={"location": "$location"},
        description="Select devices to modify interfaces on. Only devices from the selected location will be shown.",
        required=True,
    )

    interfaces = MultiObjectVar(
        label="Interfaces",
        model=Interface,
        display_field="computed_fields.device_interface",
        query_params={
            "device": "$devices",
            "include": "computed_fields",
        },
        description="Select interfaces to modify (filtered by selected devices).",
        required=True,
    )

    vlan_choice = ObjectVar(
        model=VLAN,
        query_params={"location": "$location"},
        description="Select a VLAN from the same location as the device. Defaults to a fallback VLAN based on configuration type if none selected.",
        required=False,
    )

    def run(self, config_type, location, devices, interfaces, vlan_choice):
        ### Validate location is a building
        building_type = LocationType.objects.filter(name__iexact="building").first()
        if not building_type or location.location_type != building_type:
            raise Exception(
                f"The selected location '{location.name}' is not of type 'Building'. "
                "Please select a top-level building (not a closet or MDF)."
            )

        ### Fail immediately if any trunk (tagged/tagged-all) or LAG ports are selected
        trunk_ports = [
            f"{iface.device.name} - {iface.name}"
            for iface in interfaces
            if iface.mode in ["tagged", "tagged-all"] or iface.lag is not None
        ]

        if trunk_ports:
            self.logger.error("You have selected a trunk or LAG port. Cancelling job.")
            for port in trunk_ports:
                self.logger.error(f"Trunk or LAG port: {port}")
            raise Exception(
                "You have selected a trunk or LAG interface. Only access interfaces are supported. Cancelling job."
            )

        ### Get the fallback or user-selected VLAN
        fallback_vid = self.CONFIG_DEFAULT_VLANS.get(config_type)
        selected_vlan = vlan_choice or VLAN.objects.filter(vid=fallback_vid, location=location).first()
        if not selected_vlan:
            raise Exception(
                f"No VLAN selected and fallback VLAN {fallback_vid} for config type '{config_type}' not found at location {location}."
            )

        ### Get the required tags for this config type
        tag_names = self.CONFIG_REQUIRED_TAGS.get(config_type, [])
        required_tags = set(Tag.objects.filter(name__in=tag_names))

        if len(required_tags) < len(tag_names):
            missing = set(tag_names) - {tag.name for tag in required_tags}
            raise Exception(f"Missing required tags: {', '.join(missing)}")

        ### Get 'Active' status object
        active_status = Status.objects.get(name="Active")

        ### Logging for visibility
        self.logger.info(f"Selected location: {location}")
        for device in devices:
            self.logger.info(f"- {device.name}")
        self.logger.info("Selected Interfaces:")
        for interface in interfaces:
            self.logger.info(f"- {interface.device.name} - {interface.name}")

        modified = []

        for interface in interfaces:
            ### Replace all existing tags with only the required ones
            interface.tags.set(required_tags)

            ### Set description to match config type
            interface.description = config_type.lower()

            ### Set status and enable interface
            interface.status = active_status
            interface.enabled = True

            ### Ensure mode is access if unset
            if not interface.mode:
                interface.mode = "access"

            ### Set untagged VLAN
            interface.untagged_vlan = selected_vlan

            interface.validated_save()

            modified.append(
                f"{interface.device.name} - {interface.name} (Status: Active, Enabled: True, Mode: {interface.mode}, Tags: {', '.join(tag.name for tag in required_tags)}, VLAN: {selected_vlan.vid})"
            )
            self.logger.info(
                f"Updated {interface.device.name} - {interface.name}: set status='Active', enabled=True, mode='access' (if unset), replaced tags with {tag_names}, set VLAN {selected_vlan.vid}."
            )

        if modified:
            return f"Modified {len(modified)} interfaces at {location}:\n" + "\n".join(modified)
        else:
            return "No changes were needed."


register_jobs(ModifyInterfaceConfigurations)
