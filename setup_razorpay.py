"""One-time setup: creates the Razorpay Plans backing the Pro/Premium
tiers (Razorpay Plans are immutable — a price change needs a brand new
plan, not an edit) and stores their ids in SSM, where
connectors/razorpay_connector.get_plan_id() reads them from.

Prerequisite: store your Razorpay test-mode Key ID and Key Secret in SSM
first (from the Razorpay dashboard -> Settings -> API Keys):

    AWS_PROFILE=new-account aws ssm put-parameter \\
      --name /chartink-momentum-ai/razorpay/key_id --type String --overwrite \\
      --value rzp_test_xxxxxxxxxxxx
    AWS_PROFILE=new-account aws ssm put-parameter \\
      --name /chartink-momentum-ai/razorpay/key_secret --type SecureString --overwrite \\
      --value xxxxxxxxxxxxxxxxxxxxxxxx

Then run this once:

    AWS_PROFILE=new-account python setup_razorpay.py

Re-running is safe but wasteful — it'll create duplicate Plans in Razorpay
(harmless, just clutter) rather than reuse existing ones, since Razorpay's
API has no natural idempotency key for this. Check the dashboard's Plans
list before re-running if unsure whether it already ran.
"""

import boto3

from connectors import razorpay_connector, subscription_connector

AWS_REGION = "ap-south-1"

PLAN_PARAMS = {
    "pro": "/chartink-momentum-ai/razorpay/plan_pro_id",
    "premium": "/chartink-momentum-ai/razorpay/plan_premium_id",
}


def _put_param(name, value):
    boto3.client("ssm", region_name=AWS_REGION).put_parameter(Name=name, Value=value, Type="String", Overwrite=True)


if __name__ == "__main__":
    for internal_id, ssm_param in PLAN_PARAMS.items():
        plan = subscription_connector.PLANS[internal_id]
        response = razorpay_connector.create_plan(f"Quantile {plan['name']}", plan["price_paise"], internal_id)
        _put_param(ssm_param, response["id"])
        print(f"{internal_id}: Razorpay plan {response['id']} -> stored at {ssm_param}")

    print("\nAlso store your webhook secret (Razorpay dashboard -> Settings -> Webhooks -> create one pointing at")
    print("  https://<your-domain>/api/webhooks/razorpay , events: subscription.activated, subscription.charged,")
    print("  subscription.cancelled, subscription.completed, subscription.halted):")
    print("  AWS_PROFILE=new-account aws ssm put-parameter --name /chartink-momentum-ai/razorpay/webhook_secret \\")
    print("    --type SecureString --overwrite --value <secret from the webhook you create>")
