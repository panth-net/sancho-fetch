# Sancho Fetch privacy and data flow

Sancho Fetch is local-first. It does not run a Sancho telemetry service and it
does not send fetched records, workspace contents, prompts, or API keys to
Pantheon Network.

When you ask Sancho to fetch data, Sancho sends the selected request directly
from your computer to the upstream public-data provider named for that module.
If that provider requires a credential, the credential is read locally from
the workspace's private `.env` file and sent only to that selected provider as
required by its API. Each provider has its own terms and privacy policy.

Sancho stores canonical responses, derived work, exports, logs, and private
settings in the selected local workspace. Desktop AI clients may separately
process the tool request and response under their own privacy terms. Removing a
Sancho client integration or extension preserves the workspace by default.

The provider catalog and each module's manifest identify the upstream service
and source URLs. Users should review the chosen provider's policy before
sending sensitive query parameters or credentials.
