"""Launch the IAI agent EC2 instance in ap-southeast-5.

Creates the iai-demo-agent-sg security group if it doesn't exist, finds the
latest Ubuntu 22.04 LTS AMI, launches a t3.medium with the IAI instance profile
and iai-demo key pair, waits for running state, then saves metadata to
instance_info.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

REGION = "ap-southeast-5"
INSTANCE_TYPE = "t3.medium"
IAM_INSTANCE_PROFILE = "iai-demo-agent-profile"
KEY_NAME = "iai-demo"
SG_NAME = "iai-demo-agent-sg"
TAGS = [
    {"Key": "Name", "Value": "iai-demo-agent"},
    {"Key": "Environment", "Value": "demo"},
    {"Key": "Role", "Value": "agent"},
]

# Path to the private key (expected alongside the script or at ~/.ssh/).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_KEY_CANDIDATES = [
    os.path.expanduser(f"~/.ssh/{KEY_NAME}.pem"),
    os.path.join(_SCRIPT_DIR, f"{KEY_NAME}.pem"),
]


def _ec2() -> boto3.client:
    return boto3.client("ec2", region_name=REGION)


def find_ubuntu_22_ami(ec2) -> str:
    """Return the latest Ubuntu 22.04 LTS HVM/SSD AMI ID in the region."""
    resp = ec2.describe_images(
        Owners=["099720109477"],  # Canonical's AWS account
        Filters=[
            {
                "Name": "name",
                "Values": ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"],
            },
            {"Name": "state", "Values": ["available"]},
            {"Name": "architecture", "Values": ["x86_64"]},
        ],
    )
    images = resp["Images"]
    if not images:
        raise RuntimeError("No Ubuntu 22.04 LTS AMI found in " + REGION)
    # Sort descending by creation date; take the newest.
    images.sort(key=lambda i: i["CreationDate"], reverse=True)
    ami = images[0]
    print(f"  AMI: {ami['ImageId']}  ({ami['Name']})")
    return ami["ImageId"]


def get_default_vpc_id(ec2) -> str:
    resp = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    vpcs = resp["Vpcs"]
    if not vpcs:
        raise RuntimeError("No default VPC found in " + REGION)
    return vpcs[0]["VpcId"]


def ensure_security_group(ec2, vpc_id: str) -> str:
    """Return SG ID, creating it (idempotently) if it doesn't exist."""
    # Check if it already exists.
    try:
        resp = ec2.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [SG_NAME]},
                {"Name": "vpc-id", "Values": [vpc_id]},
            ]
        )
        if resp["SecurityGroups"]:
            sg_id = resp["SecurityGroups"][0]["GroupId"]
            print(f"  Security group already exists: {sg_id}")
            return sg_id
    except ClientError:
        pass

    resp = ec2.create_security_group(
        GroupName=SG_NAME,
        Description="IAI demo agent — SSH + HTTPS inbound",
        VpcId=vpc_id,
        TagSpecifications=[
            {"ResourceType": "security-group", "Tags": TAGS},
        ],
    )
    sg_id = resp["GroupId"]
    print(f"  Created security group: {sg_id}")

    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH (demo only — restrict in prod)"}],
            },
            {
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTPS out via Telegram/AWS/GCP"}],
            },
        ],
    )
    return sg_id


def find_key_path() -> str:
    for p in _KEY_CANDIDATES:
        if os.path.exists(p):
            return p
    # Return first candidate even if missing so the info file is still useful.
    return _KEY_CANDIDATES[0]


def launch(ec2, ami_id: str, sg_id: str) -> dict:
    resp = ec2.run_instances(
        ImageId=ami_id,
        InstanceType=INSTANCE_TYPE,
        MinCount=1,
        MaxCount=1,
        KeyName=KEY_NAME,
        IamInstanceProfile={"Name": IAM_INSTANCE_PROFILE},
        SecurityGroupIds=[sg_id],
        TagSpecifications=[
            {"ResourceType": "instance", "Tags": TAGS},
        ],
        MetadataOptions={
            # IMDSv2 only — instance role credential fetch requires this.
            "HttpTokens": "required",
            "HttpEndpoint": "enabled",
        },
    )
    return resp["Instances"][0]


def wait_running(ec2, instance_id: str) -> dict:
    print(f"  Waiting for {instance_id} to reach 'running'…", end="", flush=True)
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    print(" done.")
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    return resp["Reservations"][0]["Instances"][0]


def main():
    ec2 = _ec2()
    print("[1/5] Finding latest Ubuntu 22.04 LTS AMI…")
    ami_id = find_ubuntu_22_ami(ec2)

    print("[2/5] Resolving default VPC…")
    vpc_id = get_default_vpc_id(ec2)
    print(f"  VPC: {vpc_id}")

    print("[3/5] Ensuring security group…")
    sg_id = ensure_security_group(ec2, vpc_id)

    print("[4/5] Launching instance…")
    instance = launch(ec2, ami_id, sg_id)
    instance_id = instance["InstanceId"]
    print(f"  Instance ID: {instance_id}")

    print("[5/5] Waiting for running state…")
    instance = wait_running(ec2, instance_id)

    public_ip = instance.get("PublicIpAddress", "")
    private_ip = instance.get("PrivateIpAddress", "")
    key_path = find_key_path()

    info = {
        "instance_id": instance_id,
        "public_ip": public_ip,
        "private_ip": private_ip,
        "key_path": key_path,
        "ami_id": ami_id,
        "instance_type": INSTANCE_TYPE,
        "region": REGION,
        "security_group_id": sg_id,
        "vpc_id": vpc_id,
        "launched_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = os.path.join(_SCRIPT_DIR, "instance_info.json")
    with open(out_path, "w") as f:
        json.dump(info, f, indent=2)

    print()
    print("=" * 52)
    print(f"  instance_id : {instance_id}")
    print(f"  public_ip   : {public_ip}")
    print(f"  private_ip  : {private_ip}")
    print(f"  key_path    : {key_path}")
    print(f"  saved to    : {out_path}")
    print("=" * 52)
    print()
    print(f"SSH: ssh -i {key_path} ubuntu@{public_ip}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
