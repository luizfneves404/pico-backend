from app.fcm.models import FCMDevice
from app.shared.admin import CustomModelView


class FCMDeviceAdmin(CustomModelView, model=FCMDevice):
    icon = "fa-solid fa-mobile-alt"

    column_list = (
        FCMDevice.id,
        FCMDevice.user_id,
        FCMDevice.registration_id,
        FCMDevice.device_type,
        FCMDevice.active,
        FCMDevice.created_at,
    )
    column_searchable_list = (
        FCMDevice.user_id,
        FCMDevice.registration_id,
        FCMDevice.device_type,
    )
    column_sortable_list = (
        FCMDevice.id,
        FCMDevice.user_id,
        FCMDevice.device_type,
        FCMDevice.active,
        FCMDevice.created_at,
    )
    column_details_list = (
        FCMDevice.id,
        FCMDevice.user_id,
        FCMDevice.registration_id,
        FCMDevice.device_type,
        FCMDevice.active,
        FCMDevice.created_at,
    )

    form_columns = (
        "user_id",
        "registration_id",
        "device_type",
        "active",
    )
