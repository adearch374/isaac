# isaac

## Assignment uploads

Assignments support PDF, DOC/DOCX, JPG, and PNG submissions up to 10 MB. Files are stored locally in `instance/uploads/`, which is ignored by Git. This is suitable for local development, but Render's free/starter filesystem is ephemeral, so uploaded files can be lost after a restart or redeploy. Use a Render Disk or external object storage before relying on assignment uploads in production.