# Installing Fileglancer Update Systemd Timer

## Installation Steps

1. **Copy the service and timer files to systemd directory:**
   ```bash
   sudo cp ./systemd/fileglancer-update.service /etc/systemd/system/
   sudo cp ./systemd/fileglancer-update.timer /etc/systemd/system/
   ```

2. **Edit the service file to match your environment:**
   ```bash
   sudo vim /etc/systemd/system/fileglancer-update.service
   ```

   Update these paths:
   - `WorkingDirectory=` - Path to fileglancer-janelia directory
   - `EnvironmentFile=` - Path to your .env file
   - `ExecStart=` - Full path to pixi binary (use `which pixi` to find it)

3. **Set correct permissions:**
   ```bash
   sudo chmod 644 /etc/systemd/system/fileglancer-update.service
   sudo chmod 644 /etc/systemd/system/fileglancer-update.timer
   ```

4. **Reload systemd daemon:**
   ```bash
   sudo systemctl daemon-reload
   ```

5. **Enable and start the timer:**
   ```bash
   sudo systemctl enable fileglancer-update.timer
   sudo systemctl start fileglancer-update.timer
   ```

## Verification

Check timer status:
```bash
sudo systemctl status fileglancer-update.timer
```

Check service logs:
```bash
sudo journalctl -u fileglancer-update.service -f
```

## Manual Execution

Test the service manually:
```bash
sudo systemctl start fileglancer-update.service
sudo systemctl status fileglancer-update.service
```

## Management Commands

```bash
# Stop the timer
sudo systemctl stop fileglancer-update.timer

# Disable the timer (won't start on boot)
sudo systemctl disable fileglancer-update.timer

# Restart the timer
sudo systemctl restart fileglancer-update.timer

# View recent logs
sudo journalctl -u fileglancer-update.service -n 50

# Follow logs in real-time
sudo journalctl -u fileglancer-update.service -f
```

## Notes

- The timer runs every 5 minutes after the previous run completes
- If the system was down, it will catch up on the next boot
- Logs are stored in systemd journal (use `journalctl` to view)
- All admins with sudo access can manage this timer
- The `EnvironmentFile` directive automatically exports all variables from the .env file

