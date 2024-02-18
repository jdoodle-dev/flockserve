variable "credentials_file" {
  description = "GCP credentials file"
  type        = string
}

variable "username" {
  description = "The username for ssh"
  type        = string
}

variable "project" {
  description = "The project name"
  type        = string
}

variable "ssh_public_key" {
  description = "Public SSH key for VM instance access"
  type        = string
  default     = ""
}

variable "allowed_ssh_ips" {
  description = "CIDR blocks allowed for SSH access"
  type        = list(string)
  default     = []
}

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "4.51.0"
    }
  }
}

provider "google" {
  credentials = file(var.credentials_file)
  project     = var.project
  region  = "us-central1"
  zone    = "us-central1-c"
}

resource "google_compute_network" "vpc_network" {
  name = "terraform-network"
}

resource "google_compute_instance" "vm_instance" {
  name         = "terraform-instance"
  machine_type = "c3d-highcpu-16"
  zone         = "us-central1-c"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 40
    }
  }

  network_interface {
    network = google_compute_network.vpc_network.id
    access_config {
      // This line is required for the instance to have an external IP address
    }
  }

  metadata = {
    ssh-keys = "${var.username}:${file(var.ssh_public_key)}"
  }

  service_account {
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  metadata_startup_script = <<EOF
#!/bin/bash
export USERNAME=${var.username}
cd /home/$USERNAME
sudo su $USERNAME
sudo apt-get update
sudo apt install rsync
sudo apt install python3.11-venv -y
python3 -m venv venv_flockserve
source venv_flockserve/bin/activate
pip install flockserve
wget https://raw.githubusercontent.com/jdoodle-dev/flockserve/main/examples/serving_tgi_cpu_generate.yaml
export GOOGLE_APPLICATION_CREDENTIALS=${var.credentials_file}
gcloud auth activate-service-account --key-file=$GOOGLE_APPLICATION_CREDENTIALS
gcloud config set project ${var.project}
echo "STARTING FLOCKSERVE"
whoami
sudo -u $USERNAME -H bash -c 'export GOOGLE_APPLICATION_CREDENTIALS=${var.credentials_file} &&
 gcloud auth activate-service-account --key-file=$GOOGLE_APPLICATION_CREDENTIALS &&
 gcloud config set project ${var.project} &&
 source venv_flockserve/bin/activate && flockserve --skypilot_task serving_tgi_cpu_generate.yaml'
EOF

  tags = ["http-server", "https-server", "ssh-access"]

  provisioner "file" {
    source      = var.credentials_file
    destination = "/home/${var.username}/${var.credentials_file}"

    connection {
      type        = "ssh"
      user        = var.username
      private_key = file("~/.ssh/id_ecdsa")
      host        = self.network_interface[0].access_config[0].nat_ip
    }
  }
}

resource "google_compute_firewall" "default" {
  name    = "terraform-allow-http-https"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "3000", "8000", "8080"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["http-server", "https-server"]
}

resource "google_compute_firewall" "allow_ssh" {
  name    = "terraform-allow-ssh"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.allowed_ssh_ips
  target_tags   = ["ssh-access"]
}

resource "null_resource" "vm_cleanup" {
  depends_on = [google_compute_instance.vm_instance]

  # Trigger cleanup only during destroy
  triggers = {
    instance_id = google_compute_instance.vm_instance.id
    # Pass the IP address as a trigger to be used within the provisioner
    instance_ip = google_compute_instance.vm_instance.network_interface[0].access_config[0].nat_ip
    username = var.username
  }

  provisioner "remote-exec" {
    when = destroy

    connection {
      type        = "ssh"
      user        = self.triggers.username
      private_key = file("~/.ssh/id_ecdsa")
      # Use the IP address from the trigger
      host        = self.triggers.instance_ip
    }

    inline = [
      "echo 'Performing cleanup tasks...'",
      "sudo pkill -9 flockserve || true",
      "while pgrep -x flockserve > /dev/null; do echo 'Waiting for flockserve to stop...'; sleep 1; done",
      "sudo rm /home/${self.triggers.username}/.sky/.skypilot-worker-*.lock",
      "/bin/bash -c 'source venv_flockserve/bin/activate && sky down -ya'"
    ]
  }
}