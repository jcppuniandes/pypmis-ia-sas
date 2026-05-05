from fastapi import Header


def get_tenant_id(x_tenant_id: int = Header(default=1, alias="X-Tenant-Id")) -> int:
    return x_tenant_id


def get_user_id(x_user_id: int = Header(default=1, alias="X-User-Id")) -> int:
    return x_user_id
