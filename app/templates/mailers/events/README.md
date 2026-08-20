# Email Notification Templates

These templates are used by notification emails. They're tightly coupled to the event system.
Each `EventAction` corresponds 1:1 with a potential email.

To add a notification email for an `EventAction`:

1. Make sure you've added the `EventAction` to the list of those that should generate notifications. See `EventAction`'s definition in `config/enum.py`.
1. Create a template for the email body in this directory, `[snake_case EventAction value].jinja`.
