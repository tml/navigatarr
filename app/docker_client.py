import docker


def _get_host_ports(container):
    ports = set()
    if container.ports:
        for bindings in container.ports.values():
            if bindings:
                for b in bindings:
                    if b.get('HostPort'):
                        ports.add(int(b['HostPort']))
    if not ports:
        port_bindings = (container.attrs.get('HostConfig') or {}).get('PortBindings') or {}
        for bindings in port_bindings.values():
            if bindings:
                for b in bindings:
                    if b and b.get('HostPort'):
                        ports.add(int(b['HostPort']))
    return sorted(ports)


def list_services():
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True)
        services = []
        for container in containers:
            ports = _get_host_ports(container)
            if not ports:
                continue
            tags = container.image.tags
            image = tags[0] if tags else container.image.short_id
            services.append({
                'container_id': container.id[:12],
                'name': container.name,
                'image': image,
                'status': container.status,
                'ports': ports,
            })
        return services, None
    except Exception as e:
        return [], str(e)
