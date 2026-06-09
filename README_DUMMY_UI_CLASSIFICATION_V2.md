# Netzentgelt Dummy-UI-Klassifikation V2

Geprüfter GitHub-Ausgangspunkt: `06b05d20bc3b093abbc6559c5ed6f43285a8018e`

Dieses Paket:
- ergänzt die Controller-Aktion `Als Dummy-/Planungslok markieren`
- ergänzt `91806189000-3` im pflegbaren Dummy-Katalog
- ergänzt Audit-Log und Katalog-Upsert
- korrigiert die historischen Installer-Tests nach dem Repository-Cleanup
- verändert bewusst **nicht** `scripts/verify_dummy_locomotive_hardening.py`, damit lokale Schema-Verifier-Varianten nicht überschrieben werden
- trennt Installation und Pipeline-Lauf, damit nach einem fehlgeschlagenen Dry-Run keine nachfolgenden Schritte versehentlich weiterlaufen
