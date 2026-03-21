# =============================================================================
# Story Forge Terraform Outputs
# =============================================================================

output "service_url" {
  description = "URL of the deployed Story Forge service"
  value       = google_cloud_run_v2_service.story_forge.uri
}

output "service_name" {
  description = "Name of the Cloud Run service"
  value       = google_cloud_run_v2_service.story_forge.name
}

output "service_region" {
  description = "Region where the service is deployed"
  value       = google_cloud_run_v2_service.story_forge.location
}

output "backup_bucket_name" {
  description = "Name of the GCS bucket for database backups"
  value       = coalesce(var.db_backup_bucket, google_storage_bucket.story_forge_backups[0].name)
}

output "service_account_email" {
  description = "Email of the service account used by Cloud Run"
  value       = data.google_service_account.app_runner.email
}
