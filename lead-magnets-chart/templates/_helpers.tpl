{{- define "lead-magnets.name" -}}
lead-magnets
{{- end }}

{{- define "lead-magnets.fullname" -}}
{{ .Release.Name }}
{{- end }}

{{- define "lead-magnets.labels" -}}
app.kubernetes.io/name: {{ include "lead-magnets.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
