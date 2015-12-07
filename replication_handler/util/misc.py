# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals

import logging

import kazoo.client
import yelp_lib.config_loader

from replication_handler.config import env_config
from replication_handler.models.data_event_checkpoint import DataEventCheckpoint
from replication_handler.models.database import rbr_state_session
from replication_handler.models.global_event_state import EventType
from replication_handler.models.global_event_state import GlobalEventState


KAZOO_CLIENT_DEFAULTS = {
    'timeout': 30,
}
REPLICATION_HANDLER_PRODUCER_NAME = env_config.producer_name

REPLICATION_HANDLER_TEAM_NAME = env_config.team_name

HEARTBEAT_DB = "yelp_heartbeat"

log = logging.getLogger('replication_handler.util.misc.data_event')


class ReplicationHandlerEvent(object):
    """ Class to associate an event and its position."""

    def __init__(self, event, position):
        self.event = event
        self.position = position


class DataEvent(object):
    """ Class to replace pymysqlreplication RowsEvent, since we want one
    row per event.

    Args:
        schema(string): schema/database name of event.
        table(string): table name of event.
        log_pos(int): binary log position of event.
        log_file(string): binary log file name of event.
        row(dict): a dictionary containing fields and values of the changed row.
        timestamp(int): timestamp of event, in epoch time format.
        message_type(data_pipeline.message_type): the type of event, can be CreateMessage,
          UpdateMessage, DeleteMessage or RefreshMessage.
    """

    def __init__(
        self,
        schema,
        table,
        log_pos,
        log_file,
        row,
        timestamp,
        message_type
    ):
        self.schema = schema
        self.table = table
        self.log_pos = log_pos
        self.log_file = log_file
        self.row = row
        self.timestamp = timestamp
        self.message_type = message_type


def save_position(position_data, is_clean_shutdown=False):
    if not position_data or not position_data.last_published_message_position_info:
        return
    log.info("Saving position with position data {}.".format(position_data))
    position_info = position_data.last_published_message_position_info
    topic_to_kafka_offset_map = position_data.topic_to_kafka_offset_map
    with rbr_state_session.connect_begin(ro=False) as session:
        GlobalEventState.upsert(
            session=session,
            position=position_info["position"],
            event_type=EventType.DATA_EVENT,
            cluster_name=position_info["cluster_name"],
            database_name=position_info["database_name"],
            table_name=position_info["table_name"],
            is_clean_shutdown=is_clean_shutdown,
        )
        DataEventCheckpoint.upsert_data_event_checkpoint(
            session=session,
            topic_to_kafka_offset_map=topic_to_kafka_offset_map,
            cluster_name=position_info["cluster_name"]
        )


def get_ecosystem():
    return open('/nail/etc/ecosystem').read().strip()


def get_local_zk():
    path = env_config.zookeeper_discovery_path.format(ecosystem=get_ecosystem())
    """Get (with caching) the local zookeeper cluster definition."""
    return yelp_lib.config_loader.load(path, '/')


def get_kazoo_client_for_cluster_def(cluster_def, **kwargs):
    """Get a KazooClient for a list of host-port pairs `cluster_def`."""
    host_string = ','.join('%s:%s' % (host, port) for host, port in cluster_def)

    for default_kwarg, default_value in KAZOO_CLIENT_DEFAULTS.iteritems():
        if default_kwarg not in kwargs:
            kwargs[default_kwarg] = default_value

    return kazoo.client.KazooClient(host_string, **kwargs)


def get_kazoo_client(**kwargs):
    """Get a KazooClient for a local zookeeper cluster."""
    return get_kazoo_client_for_cluster_def(get_local_zk(), **kwargs)
