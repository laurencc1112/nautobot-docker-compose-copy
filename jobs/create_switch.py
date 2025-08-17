"""
Create a Cisco access switch (SVI mgmt only, optional VC, controlled naming).

What this job does:
1) Prompts for building, room, optional rack, manufacturer (Cisco), and device model.
2) Lets you choose naming method (auto/manual) and optional role code for the name (auto selects next as# if blank).
3) Optional virtual chassis: if yes, VC is named after the base device name and the device gets named w/ .1.
4) Choose management vlan and add management IP.
5) Validates device name uniqueness (including <name>.1), IP not already in use,
   and IP falls within an existing prefix on chosen VLAN.
6) Creates the device (using the ".1" DeviceType if present), creates VC if applicable,
   creates SVI interface, assigns the IP, and sets it as primary IPv4 for the device.

Notes:
- Did not add option to auto select next mgmt IP because of first 4 reservations in infoblox.    
"""

import re
from ipaddress import ip_address, ip_interface

from nautobot.apps.jobs import (
    Job,
    register_jobs,
    ObjectVar,
    StringVar,
    ChoiceVar,
)
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Location,
    Rack,
    Interface,
    VirtualChassis,
    Manufacturer,
)
from nautobot.extras.models import Status, Role
from nautobot.ipam.models import VLAN, Prefix, IPAddress


ROLE_NAME = "BLDG_L2-Access"


class CreateSwitch(Job):
    """Create an access switch/stack, set management IP, and optional auto naming."""

    class Meta:
        name = "Create Switch"
        description = "Create an access switch/stack, set management IP, and optional auto naming."

    building = ObjectVar(
        model=Location,
        label="Building",
        required=True,
        query_params={"location_type": "Building"},
        description="Building where the device is located.",
    )

    room = ObjectVar(
        model=Location,
        label="Room/MDF/IDF",
        required=True,
        query_params={"parent": "$building"},
        description="Select the Room/IDF/MDF within the building.",
    )

    rack = ObjectVar(
        model=Rack,
        label="Rack (optional)",
        required=False,
        query_params={"location": "$room"},
        description="Select the rack if applicable.",
    )

    manufacturer = ObjectVar(
        model=Manufacturer,
        label="Manufacturer",
        required=True,
        query_params={"name__ic": "cisco"},
        description="Select the Manufacturer.",
    )

    model = ObjectVar(
        model=DeviceType,
        label="Switch Model",
        required=True,
        query_params={"manufacturer": "$manufacturer"},
        description="Choose the switch model (select the base model with no .1,.2, etc).",
    )

    role_code = StringVar(
        label="Role Code (for name only)",
        required=False,
        description="Role used only in the device name (e.g., as1, ls2). "
                    "If left blank, the next 'as#' is chosen automatically based on the closet.",
    )

    name_mode = ChoiceVar(
        label="Naming Method",
        required=True,
        choices=[("auto", "Use suggested name"), ("manual", "Enter custom name")],
        description="Use the auto suggested name from Building/Room/Role Code, or enter a custom value.",
    )

    custom_name = StringVar(
        label="Custom Device Name (Manual only)",
        required=False,
        description="Provide a custom name if 'Enter custom name' is selected.",
    )

    vc = ChoiceVar(
        label="Virtual Chassis",
        required=True,
        choices=[("yes", "Yes"), ("no", "No")],
        description="Create a Virtual Chassis and make this device the master?",
    )

    mgmt_vlan = ObjectVar(
        model=VLAN,
        label="Management VLAN",
        required=True,
        query_params={"location": "$building"},
        description="Select the management vlan.",
    )

    mgmt_ip = StringVar(
        label="Management IPv4",
        required=True,
        description="Enter a single IPv4 address, e.g., 10.1.2.10 (no mask).",
    )

    def _parse_building(self, building: Location):
        parts = str(building.name).split(':')
        bldg_num = parts[0].strip() if len(parts) >= 1 else str(building.name).strip()
        bldg_abbrev = parts[1].strip() if len(parts) >= 2 else str(building.name).strip()
        return bldg_num, bldg_abbrev

    def _parse_room(self, room: Location):
        parts = str(room.name).split(':')
        room_num = parts[1].strip() if len(parts) >= 2 else str(room.name).strip()
        k_designation = parts[2].strip() if len(parts) >= 3 else ""
        return room_num, k_designation

    def _base_name_parts(self, building: Location, room: Location):
        bldg_num, bldg_abbrev = self._parse_building(building)
        room_num, k_designation = self._parse_room(room)
        parts = [bldg_num, bldg_abbrev, room_num]
        if k_designation:
            parts.append(k_designation)
        return parts

    def _auto_role_code(self, room: Location, base_parts: list[str]) -> str:
        base_prefix = "-".join(base_parts) + "-as"
        max_n = 0
        for name in Device.objects.filter(location=room).values_list("name", flat=True):
            m = re.fullmatch(rf"{re.escape(base_prefix)}(\d+)(?:\.1)?", name, flags=re.IGNORECASE)
            if m:
                try:
                    n = int(m.group(1))
                    if n > max_n:
                        max_n = n
                except ValueError:
                    continue
        return f"as{max_n + 1 if max_n else 1}"

    def _suggest_name(self, building: Location, room: Location, role_code_text: str | None) -> str:
        base_parts = self._base_name_parts(building, room)
        if not role_code_text:
            role_code_text = self._auto_role_code(room, base_parts)
        role_code_clean = re.sub(r'[^A-Za-z0-9]+', '', role_code_text).lower() or "as1"
        base = "-".join(base_parts + [role_code_clean])
        normalized = re.sub(r'[^A-Za-z0-9\-]', '', base)
        normalized = re.sub(r'-{2,}', '-', normalized).strip('-')
        return normalized.lower()

    def _validate_name(self, name: str):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9\-]{1,62}', name):
            raise ValueError(
                f"Device name '{name}' is invalid. Use letters, digits, and dashes only; "
                "must be 2–63 characters and start with an alphanumeric."
            )

    def _assign_primary_ip(self, device, iface, host_str: str, mask_len: int, status_active):
        ip_obj, _ = IPAddress.objects.get_or_create(
            host=host_str,
            mask_length=int(mask_len),
            defaults={"status": status_active},
        )
        iface.ip_addresses.add(ip_obj)
        device.primary_ip4 = ip_obj
        device.save()
        return ip_obj

    def run(
        self,
        building,
        room,
        rack,
        manufacturer,
        model,
        name_mode,
        custom_name,
        vc,
        mgmt_vlan,
        mgmt_ip,
        role_code,
    ):
        status_active = Status.objects.get(name="Active")

        vg = mgmt_vlan.vlan_group
        vg_loc = getattr(vg, "location", None)
        if not vg or not vg_loc or vg_loc.id != building.id:
            raise ValueError(
                f"Selected VLAN '{mgmt_vlan}' belongs to VLAN Group '{vg}' at '{vg_loc}', "
                f"not the selected Building '{building}'. Choose a VLAN for this Building."
            )

        mfg_name = manufacturer.name if manufacturer else ""
        if "cisco" not in (mfg_name or "").lower():
            raise ValueError(f"Manufacturer must be Cisco (got '{mfg_name}').")
        if model.model.lower().endswith((".1", ".2", ".3", ".4")):
            raise ValueError(
                "Select the base DeviceType (without .1/.2/.3/.4); the job will select the appropriate .1 option automatically."
            )

        try:
            device_role = Role.objects.get(name=ROLE_NAME)
        except Role.DoesNotExist:
            raise ValueError(f"Required Role '{ROLE_NAME}' does not exist. Please create it first.")

        suggested_name = self._suggest_name(building, room, role_code)
        if name_mode == "manual" and custom_name:
            base_name = custom_name.strip()
            self.logger.info(f"Suggested name: {suggested_name} (ignored; using manual: {base_name}).")
        else:
            base_name = suggested_name
            self.logger.info(f"Suggested name: {suggested_name} (using auto).")

        self._validate_name(base_name)

        if Device.objects.filter(name=base_name).exists() or Device.objects.filter(name=f"{base_name}.1").exists():
            raise ValueError(f"Device name conflict: '{base_name}' or '{base_name}.1' already exists.")

        device_name = base_name
        if vc == "yes":
            if not base_name.endswith(".1"):
                device_name = f"{base_name}.1"
            else:
                device_name = base_name
                base_name = base_name[:-2]

        try:
            ip_host = ip_address(str(mgmt_ip).strip())
        except Exception:
            raise ValueError(f"'{mgmt_ip}' is not a valid IPv4 address (enter a single host IP, no mask).")

        if IPAddress.objects.filter(host=str(ip_host)).exists():
            raise ValueError(f"Management IP {ip_host} is already in use.")

        alt_model = DeviceType.objects.filter(
            manufacturer=manufacturer,
            model=f"{model.model}.1",
        ).first()
        model_to_use = alt_model or model
        if alt_model:
            self.logger.info(f"Using DeviceType variant: {alt_model.manufacturer} {alt_model.model}")
        else:
            self.logger.info(f"No '.1' variant found; using selected model: {manufacturer} {model.model}")

        device = Device.objects.create(
            name=device_name,
            device_type=model_to_use,
            role=device_role,
            status=status_active,
            location=room,
            rack=rack if rack else None,
        )
        self.logger.info(f"Created device '{device.name}' with role '{device_role}' at {room}.")

        if vc == "yes":
            vc_name = base_name
            vc_obj, _ = VirtualChassis.objects.get_or_create(name=vc_name, defaults={"master": device})
            if not vc_obj.master_id or vc_obj.master_id != device.id:
                vc_obj.master = device
                vc_obj.save()
            if not device.virtual_chassis_id or device.virtual_chassis_id != vc_obj.id or device.vc_position != 1:
                device.virtual_chassis = vc_obj
                device.vc_position = 1
                device.save()
            self.logger.info(f"Virtual Chassis '{vc_obj.name}' ensured; '{device.name}' set as master (position 1).")

        covering = (
            Prefix.objects.filter(vlan=mgmt_vlan, network__net_contains=str(ip_host)).first()
            or Prefix.objects.filter(vlan=mgmt_vlan, network__net_contains_or_equals=str(ip_host)).first()
        )
        if not covering:
            raise ValueError(
                f"{ip_host} is not inside any existing prefix associated with vlan {mgmt_vlan.vid} ({mgmt_vlan.name}). "
                "Create the appropriate prefix in IPAM first."
            )

        mask_len = covering.prefix_length
        ipi = ip_interface(f"{ip_host}/{mask_len}")

        if IPAddress.objects.filter(host=str(ipi.ip), mask_length=mask_len).exists():
            raise ValueError(f"IP address {ipi.ip}/{mask_len} is already in use in Nautobot.")

        svi_name = f"Vlan{mgmt_vlan.vid}"
        svi_iface, _ = Interface.objects.get_or_create(
            device=device,
            name=svi_name,
            defaults={"type": "virtual", "description": mgmt_vlan.name, "status": status_active, "enabled": True},
        )
        ip_obj = self._assign_primary_ip(device, svi_iface, str(ipi.ip), mask_len, status_active)
        self.logger.success(
            f"Assigned {ip_obj.host}/{ip_obj.mask_length} to {svi_iface.name} and set as Primary IPv4 "
            f"(VLAN {mgmt_vlan.vid} {mgmt_vlan.name}; Prefix {covering.network}/{covering.prefix_length})."
        )

        return f"Device '{device.name}' ready with Primary IPv4 {device.primary_ip4.host}/{device.primary_ip4.mask_length}."


register_jobs(CreateSwitch)
