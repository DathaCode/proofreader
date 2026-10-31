================================================================
  CONTROL PC -> AMAZON S3  DATABASE BACKUP  (Windows)
================================================================

This is the Windows equivalent of the webapp's nightly cron backup. It uploads
the proxy's DB files to S3 every night as dated snapshots, so you can restore
any past day.

WHAT GETS BACKED UP (from proxy_server\)
  - data\corrections.db     <- the central self-learning DB (consistent snapshot)
  - data\usage.db           <- usage logs, client names, costs (v5+, consistent snapshot)
  - data\usage_log.csv      <- old v4 request log (only if it still exists)
  - proxy_config.json       <- server settings   (set include_proxy_config=false to skip)
  NOT api_key.txt           <- the Gemini key is a SECRET and is never uploaded.

WHERE IT GOES
  s3://<your-bucket>/<prefix>/YYYY-MM-DD/...
  Old day-folders beyond "retention_days" are auto-deleted.

--------------------------------------------------------------
ONE-TIME SETUP  (on the Control PC)
--------------------------------------------------------------
1. Install the AWS CLI v2 for Windows:
      https://awscli.amazonaws.com/AWSCLIV2.msi

2. Give it credentials (an IAM user/role that can write to your bucket):
      aws configure
   (enter Access Key, Secret Key, default region e.g. ap-south-1)

3. Edit  backup_config.json  and set your bucket:
      {
        "s3_bucket": "your-lan-proxy-bucket",
        "s3_prefix": "lan-proxy-backups",
        "aws_region": "ap-south-1",     (optional; blank = aws configure default)
        "retention_days": 30,           (0 = keep everything, never prune)
        "include_proxy_config": true,
        "aws_cli": ""                   (blank = auto-detect aws.exe)
      }

4. Test it once:   double-click  BACKUP_S3.bat
   (it prints OK and writes backup.log)

5. Schedule it nightly:   run  BACKUP_SETUP.bat
   -> creates a Task Scheduler job "SinhalaProxyBackup" at 2:00 AM daily.

--------------------------------------------------------------
DAILY USE
--------------------------------------------------------------
- Nothing. It runs automatically at 2 AM (PC must be ON + this user logged in).
- History is in  backup.log .
- Run a backup on demand any time:  BACKUP_S3.bat

--------------------------------------------------------------
RESTORE A BACKUP
--------------------------------------------------------------
1. Stop the proxy:            STOP_PROXY.bat
2. Download the day you want:
      aws s3 cp s3://<bucket>/<prefix>/2026-09-01/corrections.db data\corrections.db
      aws s3 cp s3://<bucket>/<prefix>/2026-09-01/usage.db       data\usage.db
3. Start the proxy again:     START_PROXY.bat

--------------------------------------------------------------
NOTES
--------------------------------------------------------------
- The DB is copied with SQLite's online-backup API, so the backup is consistent
  even while the proxy is running (no need to stop it for the nightly job).
- Uses timestamped snapshots (NOT --delete), so it will never collide with the
  webapp's  s3://lotustech-proofreader-data/backups  mirror. Use a DIFFERENT
  bucket or prefix from the webapp.
- To run without a logged-in user, re-create the task with /ru SYSTEM and place
  the AWS credentials in the SYSTEM profile
  (C:\Windows\System32\config\systemprofile\.aws\). Simpler to keep the PC
  logged in.
================================================================
