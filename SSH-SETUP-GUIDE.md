# SSH Key Exchange — 20 Minutes to Never Go Dark Again

## Why
Buddy check detects dead bots but can't restart them without SSH access.
This one-time setup lets any bot restart any other bot automatically.

## The Machines

| Bot | User | IP | Machine |
|-----|------|----|---------|
| TARS | mharfmann | 192.168.1.234 | Matthew's Mac mini |
| Alfred | sheridanskala | 192.168.1.204 | Sheridan's Mac mini |
| Eddie V | — | 192.168.1.197 | Mark's Mac mini |
| Vex | — | 192.168.1.233 | Kent's Mac mini |

## Step 1: Generate SSH Key (if not already done)
Run this ON EACH Mac mini:
```bash
ssh-keygen -t ed25519 -C "miai-bot" -f ~/.ssh/miai_bot -N ""
```

## Step 2: Copy Key to Every Other Machine
From EACH machine, run these commands (skip the one pointing to itself):

### From Alfred's machine (192.168.1.204):
```bash
ssh-copy-id -i ~/.ssh/miai_bot.pub mharfmann@192.168.1.234    # → TARS
ssh-copy-id -i ~/.ssh/miai_bot.pub USER@192.168.1.197          # → Eddie (fill in username)
ssh-copy-id -i ~/.ssh/miai_bot.pub USER@192.168.1.233          # → Vex (fill in username)
```

### From TARS's machine (192.168.1.234):
```bash
ssh-copy-id -i ~/.ssh/miai_bot.pub sheridanskala@192.168.1.204  # → Alfred
ssh-copy-id -i ~/.ssh/miai_bot.pub USER@192.168.1.197            # → Eddie
ssh-copy-id -i ~/.ssh/miai_bot.pub USER@192.168.1.233            # → Vex
```

### From Eddie's machine (192.168.1.197):
```bash
ssh-copy-id -i ~/.ssh/miai_bot.pub sheridanskala@192.168.1.204  # → Alfred
ssh-copy-id -i ~/.ssh/miai_bot.pub mharfmann@192.168.1.234      # → TARS
ssh-copy-id -i ~/.ssh/miai_bot.pub USER@192.168.1.233            # → Vex
```

### From Vex's machine (192.168.1.233):
```bash
ssh-copy-id -i ~/.ssh/miai_bot.pub sheridanskala@192.168.1.204  # → Alfred
ssh-copy-id -i ~/.ssh/miai_bot.pub mharfmann@192.168.1.234      # → TARS
ssh-copy-id -i ~/.ssh/miai_bot.pub USER@192.168.1.197            # → Eddie
```

Each `ssh-copy-id` will ask for the remote user's password ONCE. After that, passwordless.

## Step 3: Test (30 seconds)
From each machine:
```bash
ssh -i ~/.ssh/miai_bot mharfmann@192.168.1.234 "echo TARS alive"
ssh -i ~/.ssh/miai_bot sheridanskala@192.168.1.204 "echo Alfred alive"
# etc.
```

## Step 4: Verify buddy_check Can Restart
```bash
ssh -i ~/.ssh/miai_bot sheridanskala@192.168.1.204 "openclaw gateway restart"
```
If that returns without error, we're golden.

## Who Does What
- **Sheridan**: Steps 1-3 on Alfred's machine (192.168.1.204)
- **Matthew**: Steps 1-3 on TARS's machine (192.168.1.234)  
- **Mark**: Steps 1-3 on Eddie's machine (192.168.1.197) — need your username
- **Kent**: Steps 1-3 on Vex's machine (192.168.1.233) — need your username

## Missing Info Needed:
- [ ] Username on Mark's Mac mini (192.168.1.197)
- [ ] Username on Kent's Mac mini (192.168.1.233)
- [ ] Confirm all 4 machines have SSH enabled (System Settings → General → Sharing → Remote Login ON)
