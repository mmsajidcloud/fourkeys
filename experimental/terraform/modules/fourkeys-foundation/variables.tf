variable "project_id" {
  type = string
  description = "Project ID of the target project."
}

variable "region" {
  type    = string
  description = "Region to deploy resources."
  default = "us-central1"
}

variable "enable_apis" {
  type = bool 
  description = "Toggle to include required APIs."
  default = false
}