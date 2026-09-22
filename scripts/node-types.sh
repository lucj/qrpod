kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{" => "}{.metadata.labels.node\.kubernetes\.io\/instance-type}{"\n"}{end}'
