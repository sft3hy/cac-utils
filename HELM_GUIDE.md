# Helm Chart Orchestration Guide

Helm simplifies Kubernetes by packaging resources into a single, versioned unit. This guide breaks down a professional "project-first" chart, focusing on real-world requirements like GPU access and secure private registries.

---

## 1. Quick Start: The `gpu-app` Project

This sample project is an "immediately working" chart for specialized AI/Vision workloads.

### **Chart.yaml**
The `Chart.yaml` file defines the identity of your application.

```yaml
apiVersion: v2
name: gpu-app
description: A production-ready GPU-accelerated application
type: application
version: 1.0.0
appVersion: "1.0.0"
```
#### **Eplanation**
- **`apiVersion: v2`**: Indicates this chart is designed for Helm 3.
- **`name: gpu-app`**: The unique name of your package. This name should match the directory it resides in.
- **`type: application`**: Declares this as an installable app (rather than a "library" chart used only for dependency sharing).
- **`version: 1.0.0`**: The version of the *Helm package*. Increment this whenever you modify the chart's structure or template logic.
- **`appVersion: "1.0.0"`**: The version of the *underlying software*. This is usually your Docker image tag (e.g., your code release 1.0.0).

---

### **values.yaml**
This is the "Configuration Interface" used to inject data into templates.

```yaml
# Private Registry Authentication
imagePullSecrets:
  - name: internal-harbor-registry

# Default Scheduling (CPU nodes)
tolerations:
  - key: "project"
    operator: "Equal"
    effect: "NoSchedule"
    value: "cosmichorizon"

# Specialized Scheduling (GPU nodes)
tolerationsGPU:
  - key: "nvidia.com/gpu"
    operator: "Equal"
    effect: "NoSchedule"
    value: "true"

# Vision Service Configuration
vision:
  replicaCount: 1
  image:
    repository: harbor.i2cv.io/cosmichorizon/vision-model
    tag: latest
  resources:
    limits:
      nvidia.com/gpu: 1
      cpu: "2"
      memory: "4Gi"
    requests:
      cpu: "1"
      memory: "2Gi"

service:
  type: ClusterIP
  port: 8080
```
#### **Eplanation**
- **`imagePullSecrets`**: Provides credentials for Kubernetes to pull images from secure registries like Harbor.
- **`tolerationsGPU`**: Specialized scheduling logic. These are used when nodes are "tainted" to reserve GPU hardware for specific projects, preventing generic workloads from occupying expensive resources.
- **`resources`**:
    - **`limits`**: The maximum CPU/RAM a pod can consume. If a pod hits its memory limit, it is killed (OOMKilled).
    - **`requests`**: The minimum resources the scheduler must find available on a node before it can place the pod there.
- **`vision.image`**: Grouping configuration into logical blocks (like `vision`) makes it easier to scale complex charts with multiple components.

---

### **templates/_helpers.tpl**
Helm "helpers" allow you to write reusable logic snippets.

```yaml
{{- define "gpu-app.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "gpu-app.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
```
#### **Eplanation**
- **`{{- define ... -}}`**: Creates a named template that can be called repeatedly elsewhere in the chart.
- **`default .Chart.Name`**: A fallback mechanism. Use the chart name unless the user provides a custom `nameOverride` in `values.yaml`.
- **`trunc 63`**: Vital for Kubernetes stability. Resource names (like Services or Pods) cannot exceed 63 characters due to DNS limitations.
- **`fullname` Logic**: Dynamically joins the release name (e.g., `prod-env`) with the app name to create unique, non-clashing resources.

---

### **templates/deployment.yaml**
The core orchestration manifest defining how your container runs.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "gpu-app.fullname" . }}
  labels:
    {{- include "gpu-app.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.vision.replicaCount }}
  selector:
    matchLabels:
      {{- include "gpu-app.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "gpu-app.selectorLabels" . | nindent 8 }}
        component: vision
    spec:
      imagePullSecrets:
        {{- toYaml .Values.imagePullSecrets | nindent 8 }}
      containers:
        - name: vision
          image: "{{ .Values.vision.image.repository }}:{{ .Values.vision.image.tag }}"
          ports:
            - containerPort: 8080
          resources:
            {{- toYaml .Values.vision.resources | nindent 12 }}
      
      # Node Scaling Integration
      {{- with .Values.tolerationsGPU }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
```
#### **Eplanation**
- **`matchLabels`**: The "link" between the Deployment and its Pods. The Deployment uses these labels to track and maintain the state of its containers.
- **`toYaml ... | nindent 8`**: This syntax takes a complex object from `values.yaml` (like the list of secrets) and dumps it directly into the template while indenting it by 8 spaces.
- **`{{- with ... }}`**: A scoping tool. If `tolerationsGPU` exists in `values.yaml`, this block executes, injecting the scheduling rules at the bottom of the Pod spec.

---

### **templates/service.yaml**
Networking manifest providing a stable DNS name for ephemeral pods.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "gpu-app.fullname" . }}
  labels:
    {{- include "gpu-app.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: 8080
      protocol: TCP
  selector:
    {{- include "gpu-app.selectorLabels" . | nindent 4 }}
```
#### **Eplanation**
- **`type: {{ .Values.service.type }}`**: Typically `ClusterIP` (internal) or `LoadBalancer` (external).
- **`port` vs `targetPort`**:
    - **`port`**: The port number exposed to the *outside world* (or other components in the cluster).
    - **`targetPort`**: The port number on which the *actual application* (container) is listening.
- **`selector`**: Critical routing. Traffic arriving on the Service is automatically forwarded to any pod matching these labels.

---

## 2. Core Concepts Reference

- **Indentation is everything**: YAML failures in Helm are usually just 2 extra spaces. Use `nindent` to keep your formatting clean.
- **Scheduling Logic**: Use **Taints** on nodes and **Tolerations** on pods to ensure your heavy GPU workloads don't accidentally compete with lightweight API services.
- **Health Checks**: Always include `livenessProbe` and `readinessProbe` in your real deployments to ensure Kubernetes can restart unhealthy containers automatically.

---

## 3. Registry & Operations

Once your chart is ready, use these standard commands to build your images and publish your chart to a registry like Harbor.

### **Docker Operations**
Building and pushing the underlying application image.

```bash
# 1. Log in to the registry
docker login harbor.i2cv.io

# 2. Build and tag your image
docker build -t harbor.i2cv.io/cosmichorizon/sample-image:latest .

# 3. Publish the image for Kubernetes to access
docker push harbor.i2cv.io/cosmichorizon/sample-image:latest
```

### **Helm Operations (OCI)**
Packaging and pushing your chart to an OCI-compliant registry.

```bash
# 1. Log in to the Helm registry
helm registry login harbor.i2cv.io/cosmichorizon

# 2. Package and push the chart (OCI)
# Note: increment the chart version in Chart.yaml first
helm push sample-chart-0.1.0.tgz oci://harbor.i2cv.io/cosmichorizon

# 3. Deploy from local directory
helm upgrade --install my-release-name ./gpu-app
```

---
> [!TIP]
> **Pro Tip**: Always push your images *before* pushing your chart to ensure the `appVersion` matches a valid image tag in the registry.