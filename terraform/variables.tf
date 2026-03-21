# =============================================================================
# Story Forge Terraform Variables
# =============================================================================

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "story_forge_image" {
  description = "Container image URL for Story Forge"
  type        = string
  default     = "gcr.io/PROJECT_ID/story-forge:latest"
}

variable "db_backup_bucket" {
  description = "GCS bucket name for database backups"
  type        = string
  default     = ""
}
