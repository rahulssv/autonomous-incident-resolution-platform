{{- define "airp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "airp.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "airp.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

