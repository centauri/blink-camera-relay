# Security

Do not expose this proof of concept to the public Internet. The native Windows dashboard binds
to loopback. Container mode listens on the LAN and requires an admin password;
HTTP Basic credentials are not encrypted without TLS or a VPN. RTSP and the ONVIF adapter currently have no enforced client
credentials. Protect adoption accepting a username/password does not establish
that the adapter authenticates them. Use a trusted, isolated camera network.

Blink account tokens and credentials belong only in local data/ and .env files.
Never attach them, raw API responses, video frames, logs, or private camera URLs
to an issue. Stored credentials are sensitive plaintext protected by host file
permissions, not an encrypted vault. TLS verification is enabled; an optional
explicit certificate pin must be independently verified before use.

For a vulnerability, use the repository's private security-reporting feature
if enabled. Otherwise contact the maintainer privately before disclosing exploit
or account details. Ordinary redacted bug reports can use GitHub issues.
