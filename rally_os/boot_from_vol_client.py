from oslo_config import cfg
from novaclient.v2 import servers
from novaclient.v2 import images


CONF = cfg.CONF

OSCLIENTS_OPTS = [
    cfg.IntOpt("nova_server_volume_size", default=5,
                 help="Size of volume in GB that'll be used to launch VM")
]
CONF.register_opts(OSCLIENTS_OPTS)


def enforce_boot_from_volume(client):
    """Add boot from volume args in create server method call
    """
    class ServerManagerBFV(servers.ServerManager):

        def __init__(self, client):
            super(ServerManagerBFV, self).__init__(client)
            self.bfv_image_client = images.ImageManager(client)
        
        def create(self, name, image, flavor, **kwargs):
            image_obj = self.bfv_image_client.get(image)
            if "block_device_mapping" not in image_obj.metadata.keys() and \
                 not "block_device_mapping_v2" in kwargs.keys() and \
               not "block_device_mapping" in kwargs.keys():
                if 'volume_size' in kwargs:
                    vol_size = kwargs.pop('volume_size')
                else:
                    vol_size = CONF.nova_server_volume_size
                bv_map = [{
                        "source_type": "image",
                        "destination_type": "volume",
                        "delete_on_termination": "1",
                        "boot_index": 0,
                        "uuid": image,
                        "device_name": "vda",
                        "volume_size": str(vol_size)}]
                bdm_args = {
                'block_device_mapping_v2' : bv_map,
                }
                kwargs.update(bdm_args)
                image = ''
            return super(ServerManagerBFV, self).create(name, image,
                                                    flavor, **kwargs)
    client.servers = ServerManagerBFV(client)

