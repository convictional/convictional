terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.19.0"
    }
  }

  # Partial backend configuration: the state bucket is specific to your GCP
  # project, so supply it at init time rather than committing it here.
  #
  #   tofu init \
  #     -backend-config="bucket=your-terraform-state-bucket" \
  #     -backend-config="prefix=convictional-production"
  #
  # Create the bucket first, with versioning enabled, and never point two
  # environments at the same prefix.
  backend "gcs" {}
}

provider "google" {
  project = local.project_id
  region  = local.region
}

provider "google-beta" {
  project = local.project_id
  region  = local.region
}
