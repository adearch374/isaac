# isaac

## Deploying with Firebase Hosting and Cloud Run

The app already includes Gunicorn. `Procfile` configures the Cloud Run source
build to start it on the port provided by Cloud Run, and `firebase.json` routes
Firebase Hosting requests to the Cloud Run service named `isaac` in
`us-central1`. Change the service name or region in `firebase.json` if you
deploy with different values. Use the same Google Cloud/Firebase project for
both services and enable billing for Cloud Run and Hosting rewrites.

1. Select the Google Cloud project to use for both Firebase and Cloud Run:

   ```sh
   gcloud config set project YOUR_PROJECT_ID
   ```

2. Before deploying, configure a persistent PostgreSQL database and create
   Secret Manager secrets named `isaac-secret` and `isaac-database-url`.
   Store a unique Flask `SECRET_KEY` and the database connection URL in those
   secrets. Grant the Cloud Run service identity permission to access them.
   Do not use the default SQLite database for production: Cloud Run's
   container filesystem is ephemeral and each instance has its own copy.

3. Deploy the backend:

   ```sh
   gcloud run deploy isaac \
     --source . \
     --region us-central1 \
     --allow-unauthenticated \
     --set-secrets=SECRET_KEY=isaac-secret:latest,DATABASE_URL=isaac-database-url:latest
   ```

4. Link Firebase CLI to the same project, then deploy Hosting:

   ```sh
   firebase use --add
   firebase deploy --only hosting
   ```

Firebase Hosting serves `firebase-public/health-check.txt` directly; other
requests, including the Flask app's `/static/...` assets, are rewritten to
Cloud Run. Add or change static files in `firebase-public` only when they
should be served by Hosting instead of Flask.

Cloud Run may scale to zero, so an instance can still have a cold start.
Keeping a minimum instance running can reduce cold starts but may incur
additional charges. Assignment uploads in `instance/uploads/` and uploaded
gallery images in `static/images/gallery/` are also local to a container
instance; use persistent object storage before relying on uploads in
production.

## Assignment uploads

Assignments support PDF, DOC/DOCX, JPG, and PNG submissions up to 10 MB. Files are stored locally in `instance/uploads/`, which is ignored by Git. This is suitable for local development, but Render's free/starter filesystem is ephemeral, so uploaded files can be lost after a restart or redeploy. Use a Render Disk or external object storage before relying on assignment uploads in production.
