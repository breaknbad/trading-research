# TOOLS.md - Local Setup Notes

> Local tools, credentials, and environment-specific details.

## APIs & Services

| Service | Status | Notes |
|---------|--------|-------|
| Discord | ✅ | Bot token configured, guild + DMs active |

## Remote Access

- **SSH enabled** on Mac mini
- **Local IP:** 192.168.1.204 | **User:** sheridanskala | **Port:** 22
- **Client:** Termius (Matthew's phone/desktop)
- **Note:** Local network only — no Tailscale/VPN yet

## Bot Infrastructure

| Bot | Discord ID | Machine | IP |
|-----|-----------|---------|-----|
| TARS | 1474972952368775308 | Matthew's Mac mini | 192.168.1.234 |
| Alfred | 1474950973997973575 | Sheridan's Mac mini | 192.168.1.204 |
| Vex | 1474965154293612626 | Kent's Mac mini | 192.168.1.233 |
| givvygoblin / Eddie V | 1475265797180882984 | Mark's Mac mini | — |

All bots run on separate machines. No shared filesystem. Discord is the only comms channel.

## Discord Server
- **Guild ID:** 1474951427511029820
- **Web Design channel:** 1475736326086201426

## Common Commands

```bash
openclaw gateway status
openclaw gateway restart
openclaw pairing approve discord <CODE>
```

---

*Update as tools and integrations are added.*
