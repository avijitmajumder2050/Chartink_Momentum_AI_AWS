"""Promote/demote a user's role by adding/removing them from the Cognito
"admin" group — there's no in-app user-management UI yet, so this is the
way to grant admin access. A user with no group membership is a
"subscriber" by default (see app.py's _role_from_groups()), so there's
nothing to do to make someone a plain subscriber.

Usage:
    AWS_PROFILE=new-account python manage_user_roles.py promote you@example.com
    AWS_PROFILE=new-account python manage_user_roles.py demote you@example.com
    AWS_PROFILE=new-account python manage_user_roles.py list
"""

import sys

import boto3

USER_POOL_ID = "ap-south-1_rBcLm6WvY"
REGION = "ap-south-1"
ADMIN_GROUP = "admin"


def _client():
    return boto3.client("cognito-idp", region_name=REGION)


def promote(email):
    _client().admin_add_user_to_group(UserPoolId=USER_POOL_ID, Username=email, GroupName=ADMIN_GROUP)
    print(f"{email} is now an admin. They'll see the change next time they log in or their session refreshes (up to 60 min).")


def demote(email):
    _client().admin_remove_user_from_group(UserPoolId=USER_POOL_ID, Username=email, GroupName=ADMIN_GROUP)
    print(f"{email} is back to a plain subscriber.")


def list_admins():
    response = _client().list_users_in_group(UserPoolId=USER_POOL_ID, GroupName=ADMIN_GROUP)
    users = response.get("Users", [])
    if not users:
        print("No admins yet.")
        return
    for user in users:
        attrs = {a["Name"]: a["Value"] for a in user["Attributes"]}
        print(attrs.get("email", user["Username"]))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("promote", "demote", "list"):
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == "list":
        list_admins()
    else:
        if len(sys.argv) < 3:
            print(f"Usage: python manage_user_roles.py {command} <email>")
            sys.exit(1)
        (promote if command == "promote" else demote)(sys.argv[2])
