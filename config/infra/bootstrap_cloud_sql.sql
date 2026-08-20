--- Grants the application's IAM service accounts ownership of, and access to,
--- a freshly created database. Run once per database, as the `postgres` user,
--- after `tofu apply` has provisioned the Cloud SQL instance.
---
--- Every value in the DECLARE block below has to be set for your environment,
--- including db_name — it defaults to what environments/example passes as the
--- module's db_name, so it is easy to miss if yours differs. Cloud SQL IAM
--- usernames are the service account email with the ".gserviceaccount.com"
--- suffix removed, so convictional-app@my-project.iam.gserviceaccount.com becomes
--- convictional-app@my-project.iam.
---
--- Set eng and eng_write to NULL if you did not configure
--- engineering_group_email on the app module.
DO $$
DECLARE
    --- Must match the db_name you passed to the app module.
    db_name text := 'convictional_production';
	deploy text := 'convictional-deploy@<project-id>.iam';
	app text := 'convictional-app@<project-id>.iam';
	eng text := '<engineering-group-email>';
	eng_write text := 'convictional-eng-write@<project-id>.iam';
	owner text;
	resource text;
BEGIN
    --- Grant permissions to app and deploy users
    FOREACH owner IN ARRAY ARRAY[deploy, app] LOOP
        --- Execute statements are required because these are DDL statements
        EXECUTE format('GRANT cloudsqlsuperuser TO %I', owner);
        EXECUTE format('GRANT USAGE, CREATE on SCHEMA public TO %I', owner);

        --- Become the user and set default privileges for resources created by them
        EXECUTE format('GRANT %I TO current_user', owner);
        EXECUTE format('SET ROLE %I', owner);
	    FOREACH resource IN ARRAY ARRAY['TABLES', 'SEQUENCES'] LOOP
            --- Full permissions
			EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT ALL PRIVILEGES ON %s TO %I', owner, resource, deploy);
			EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT ALL PRIVILEGES ON %s TO %I', owner, resource, app);

            IF eng_write IS NOT NULL THEN
				EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT ALL PRIVILEGES ON %s TO %I', owner, resource, eng_write);
            END IF;

            --- Read-only permissions
            IF eng IS NOT NULL THEN
				EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON %s TO %I', owner, resource, eng);
            END IF;
		END LOOP;

        --- Reset role to current user and revoke permissions used to become other user
        RESET ROLE;
        EXECUTE format('REVOKE %I FROM current_user', owner);
	END LOOP;

    --- Ensure deploy account owns the database
    EXECUTE format('GRANT %I TO current_user', deploy);
    EXECUTE format('ALTER DATABASE %I OWNER TO %I', db_name, deploy);
    EXECUTE format('REVOKE %I FROM current_user', deploy);

    --- Create extensions
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
END $$;
