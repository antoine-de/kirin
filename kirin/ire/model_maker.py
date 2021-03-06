# Copyright (c) 2001-2015, Canal TP and/or its affiliates. All rights reserved.
#
# This file is part of Navitia,
#     the software to build cool stuff with public transport.
#
# Hope you'll enjoy and contribute to this project,
#     powered by Canal TP (www.canaltp.fr).
# Help us simplify mobility and open public transport:
#     a non ending quest to the responsive locomotion way of traveling!
#
# LICENCE: This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Stay tuned using
# twitter @navitia
# IRC #navitia on freenode
# https://groups.google.com/d/forum/navitia
# www.navitia.io
import logging
from datetime import timedelta
from dateutil import parser
from kirin.core import model

# For perf benches:
# http://effbot.org/zone/celementtree.htm
import xml.etree.cElementTree as ElementTree
from kirin.exceptions import InvalidArguments, ObjectNotFound
import navitia_wrapper


def get_node(elt, xpath):
    """
    get a unique element in an xml node
    raise an exception if the element does not exists
    """
    res = elt.find(xpath)
    if res is None:
        raise InvalidArguments('invalid xml, impossible to find "{node}" in xml elt {elt}'.format(
            node=xpath, elt=elt.tag))
    return res


def get_value(elt, xpath):
    node = get_node(elt, xpath)
    return node.text if node is not None else None


def as_date(s):
    if s is None:
        return None
    return parser.parse(s, dayfirst=True, yearfirst=False)


def to_str(date):
    return date.strftime("%Y%m%dT%H%M%S")


def headsign(str):
    """
    we remove leading 0 for the headsigns
    """
    return str.lstrip('0')


def as_bool(s):
    return s == 'true'


def get_navitia_stop_time(navitia_vj, stop_id):
    nav_st = next((st for st in navitia_vj['stop_times']
                  if st.get('journey_pattern_point', {})
                       .get('stop_point', {})
                       .get('id') == stop_id), None)

    # if a VJ pass several times at the same stop, we cannot know
    # perfectly which stop time to impact
    # as a first version, we only impact the first

    return nav_st


class KirinModelBuilder(object):

    def __init__(self, nav):
        self.navitia = nav

    def build(self, rt_update):
        """
        parse raw xml in the rt_update object
        and return a list of trip updates

        The TripUpdates are not yet associated with the RealTimeUpdate
        """
        try:
            root = ElementTree.fromstring(rt_update.raw_data)
        except ElementTree.ParseError as e:
            raise InvalidArguments("invalid xml: {}".format(e.message))

        if root.tag != 'InfoRetard':
            raise InvalidArguments('{} is not a valid xml root, it must be "InfoRetard"'.format(root.tag))

        vjs = self.get_vjs(get_node(root, 'Train'))

        # TODO handle also root[DernierPointDeParcoursObserve] in the modification
        trip_updates = [self.make_trip_update(vj, get_node(root, 'TypeModification')) for vj in vjs]

        return trip_updates

    def get_vjs(self, xml_train):
        log = logging.getLogger(__name__)
        train_number = headsign(get_value(xml_train, 'NumeroTrain'))  # TODO handle parity in train number

        # to get the date of the vj we use the start/end of the vj + some tolerance
        # since the ire data and navitia data might not be synchronized
        vj_start = as_date(get_value(xml_train, 'OrigineTheoriqueTrain/DateHeureDepart'))
        since = vj_start - timedelta(hours=1)
        vj_end = as_date(get_value(xml_train, 'TerminusTheoriqueTrain/DateHeureTerminus'))
        until = vj_end + timedelta(hours=1)

        log.debug('searching for vj {} on {} in navitia'.format(train_number, vj_start))

        navitia_vjs = self.navitia.vehicle_journeys(q={
            'headsign': train_number,
            'since': to_str(since),
            'until': to_str(until),
            'depth': '2',  # we need this depth to get the stoptime's stop_area
            'show_codes': 'true'  # we need the stop_points CRCICH codes
        })

        if not navitia_vjs:
            raise ObjectNotFound(
                'impossible to find train {t} on [{s}, {u}['.format(t=train_number,
                                                                    s=since,
                                                                    u=until))

        vjs = []
        for nav_vj in navitia_vjs:
            vj = model.VehicleJourney(nav_vj, vj_start.date())
            vjs.append(vj)

        return vjs

    def make_trip_update(self, vj, xml_modification):
        """
        create the TripUpdate object
        """
        trip_update = model.TripUpdate(vj=vj)

        delay = xml_modification.find('HoraireProjete')
        if delay:
            trip_update.status = 'update'
            for downstream_point in delay.iter('PointAval'):
                # we need only to consider the station
                if not as_bool(get_value(downstream_point, 'IndicateurPRGare')):
                    continue
                nav_st = self.get_navitia_stop_time(downstream_point, vj.navitia_vj)

                if nav_st is None:
                    continue

                nav_stop = nav_st.get('stop_point', {})

                departure = None
                arrival = None
                st_update = model.StopTimeUpdate(nav_stop, departure, arrival)
                trip_update.stop_time_updates.append(st_update)

        removal = xml_modification.find('Suppression')
        if removal:
            if get_value(removal, 'TypeSuppression') == 'T':
                trip_update.status = 'delete'
                trip_update.stop_time_updates = []
            elif get_value(removal, 'TypeSuppression') == 'P':
                trip_update.status = 'update'

        return trip_update

    def get_navitia_stop_time(self, downstream_point, nav_vj):
        """
        get a navitia stop from an xml node
        the xml node MUST contains a CR, CI, CH tags

        it searchs in the vj's stops for a stop_area with the external code
        CR-CI-CH
        """
        cr = get_value(downstream_point, 'CRPR')
        ci = get_value(downstream_point, 'CIPR')
        ch = get_value(downstream_point, 'CHPR')

        nav_external_code = "{cr}-{ci}-{ch}".format(cr=cr, ci=ci, ch=ch)

        nav_stop_times = []
        for s in nav_vj.get('stop_times', []):
            for c in s.get('stop_point', {}).get('stop_area', {}).get('codes', []):
                if c['value'] == nav_external_code and c['type'] == 'CR-CI-CH':
                    nav_stop_times.append(s)
                    break

        if not nav_stop_times:
            logging.getLogger(__name__).info('impossible to find stop "{}" in the vj, skipping it'
                                             .format(nav_external_code))
            return None

        if len(nav_stop_times) > 1:
            logging.getLogger(__name__).warning('too many stops found for code "{}" in the vj, '
                                                'we take the first one'
                                                .format(nav_external_code))

        return nav_stop_times[0]
