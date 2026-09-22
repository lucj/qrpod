kubectl get pods --field-selector=status.phase=Pending --no-headers | wc -l
