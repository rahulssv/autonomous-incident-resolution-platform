<#
Creates a PEM bundle from certificates in the LocalMachine Root store and
configures Python/requests SSL environment variables at user scope.

Run in PowerShell:
	.\Cert-Solution-Windows.ps1
#>

Write-Host "[INFO] Building a certificate bundle from Windows trusted root certificates..."

$base64Certs = Get-ChildItem -Path Cert:\LocalMachine\Root |
	Select-Object -Unique |
	ForEach-Object {
		@"
# Issuer: $($_.Issuer)
# Subject: $($_.Subject)
-----BEGIN CERTIFICATE-----
$([Convert]::ToBase64String($_.Export('Cert'), [System.Base64FormattingOptions]::InsertLineBreaks))
-----END CERTIFICATE-----
"@
	}

if (-not $base64Certs -or $base64Certs.Count -eq 0) {
	Write-Error "No certificates were found in Cert:\LocalMachine\Root. Run PowerShell as Administrator and try again."
	exit 1
}

$certsString = $base64Certs -join "`n`n"

$certFileName = "generated-cert-bundle.pem"
$certFile = New-Item -Path $HOME -Name $certFileName -ItemType File -Value $certsString -Force

# Persist for future PowerShell sessions.
[Environment]::SetEnvironmentVariable("SSL_CERT_FILE", $certFile.FullName, "User")
[Environment]::SetEnvironmentVariable("REQUESTS_CA_BUNDLE", $certFile.FullName, "User")

# Apply immediately for the current PowerShell session too.
$env:SSL_CERT_FILE = $certFile.FullName
$env:REQUESTS_CA_BUNDLE = $certFile.FullName

Write-Host "[SUCCESS] Certificate bundle created: $($certFile.FullName)"
Write-Host "[SUCCESS] User environment variables configured: SSL_CERT_FILE and REQUESTS_CA_BUNDLE"
Write-Host "[NEXT] Open a new terminal (recommended), or continue in this terminal where variables are already set."