# Example consumption data (replace with DB query later)
current_consumption = 520  # in kWh
threshold = 600  # set your threshold

# Fake email configuration (for display only)
sender_email = "ososinelson4@gmail.com"
receiver_email = "barongonelson92@gmail.com"

def send_alert(consumption):
    subject = "EcoPulse Alert: High Energy Consumption"
    body = f"""
    Dear User,

    Your household electricity consumption has reached {consumption} kWh,
    which is above the set threshold of {threshold} kWh.

    Please check your appliances and consider reducing usage.

    Regards,
    EcoPulse Monitoring System
    """

    # Instead of sending, just print the simulated email
    print("----- Simulated Alert Email -----")
    print(f"From: {sender_email}")
    print(f"To: {receiver_email}")
    print(f"Subject: {subject}")
    print(body.strip())
    print("---------------------------------")

# Run the alert check
if current_consumption > threshold:
    send_alert(current_consumption)
else:
    print("Consumption is within safe limits.")
