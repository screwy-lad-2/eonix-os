# Eonix OS Linux Scripts

## Install (one command)

```bash
bash install/eonix-install.sh
```

## Set as login shell (Linux only)

```bash
sudo cp docs/scripts/eonix-shell-wrapper.sh /usr/local/bin/eonix-shell
sudo chmod +x /usr/local/bin/eonix-shell
echo '/usr/local/bin/eonix-shell' | sudo tee -a /etc/shells
chsh -s /usr/local/bin/eonix-shell
```

## Start all agents

```bash
bash start_eonix.sh
```

## Uninstall

```bash
bash install/eonix-install.sh --uninstall
```
