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

import pytest
from kirin.core.handler import handle
from kirin.core.model import RealTimeUpdate, TripUpdate, VehicleJourney, StopTimeUpdate
import datetime
from kirin import app, db
from tests.check_utils import _dt


def create_trip_update(id, trip_id, circulation_date, stops):
    trip_update = TripUpdate()
    trip_update.id = id
    vj = VehicleJourney({'id': trip_id}, circulation_date)
    trip_update.vj = vj
    for stop in stops:
        st = StopTimeUpdate({'id': stop['id']}, stop['departure'], stop['arrival'])
        st.arrival_status = stop['arrival_status']
        st.departure_status = stop['departure_status']
        trip_update.stop_time_updates.append(st)

    db.session.add(vj)
    db.session.add(trip_update)
    return trip_update

@pytest.fixture()
def setup_database():
    """
    we create two realtime_updates with the same vj but for different date
    and return a vj for navitia
    """
    with app.app_context():
        vju = create_trip_update('70866ce8-0638-4fa1-8556-1ddfa22d09d3', 'vehicle_journey:1', datetime.date(2015, 9, 8),
                [
                    {'id': 'sa:1', 'departure': _dt("8:15"), 'arrival': None, 'departure_status': 'update', 'arrival_status': 'none'},
                    {'id': 'sa:2', 'departure': _dt("9:10"), 'arrival': _dt("9:05"), 'departure_status': 'none', 'arrival_status': 'none'},
                    {'id': 'sa:3', 'departure': None, 'arrival': _dt("10:05"), 'departure_status': 'none', 'arrival_status': 'none'},
                    ])
        rtu = RealTimeUpdate(None, 'ire')
        rtu.id = '10866ce8-0638-4fa1-8556-1ddfa22d09d3'
        rtu.trip_updates.append(vju)
        db.session.add(rtu)
        vju = create_trip_update('70866ce8-0638-4fa1-8556-1ddfa22d09d4', 'vehicle_journey:1', datetime.date(2015, 9, 7),
                [
                    {'id': 'sa:1', 'departure': _dt("8:35", day=7), 'arrival': None, 'departure_status': 'update', 'arrival_status': 'none'},
                    {'id': 'sa:2', 'departure': _dt("9:40", day=7), 'arrival': _dt("9:35", day=7), 'departure_status': 'update', 'arrival_status': 'update'},
                    {'id': 'sa:3', 'departure': None, 'arrival': _dt("10:35", day=7), 'departure_status': 'none', 'arrival_status': 'update'},
                    ])
        rtu = RealTimeUpdate(None, 'ire')
        rtu.id = '20866ce8-0638-4fa1-8556-1ddfa22d09d3'
        rtu.trip_updates.append(vju)
        db.session.add(rtu)
        db.session.commit()

@pytest.fixture()
def navitia_vj():
    return {'id': 'vehicle_journey:1', 'stop_times': [
        {'arrival_time': None, 'departure_time': datetime.time(8, 10), 'stop_point': {'id': 'sa:1'}},
        {'arrival_time': datetime.time(9, 5), 'departure_time': datetime.time(9, 10), 'stop_point': {'id': 'sa:2'}},
        {'arrival_time': datetime.time(10, 5), 'departure_time': None, 'stop_point': {'id': 'sa:3'}}
        ]}


def test_handle_basic():
    with pytest.raises(TypeError):
        handle(None)

    #a RealTimeUpdate without any TripUpdate doesn't do anything
    with app.app_context():
        real_time_update = RealTimeUpdate(raw_data=None, connector='ire')
        res = handle(real_time_update, [])
        assert res == real_time_update


def test_handle_new_vj():
    """an easy one: we have one vj with only one stop time updated"""
    navitia_vj = {'id': 'vehicle_journey:1', 'stop_times': [
        {'arrival_time': None, 'departure_time': datetime.time(8, 10), 'stop_point': {'id': 'sa:1'}},
        {'arrival_time': datetime.time(9, 10), 'departure_time': None, 'stop_point': {'id': 'sa:2'}}
        ]}
    with app.app_context():
        trip_update = TripUpdate()
        vj = VehicleJourney(navitia_vj, datetime.date(2015, 9, 8))
        trip_update.vj = vj
        trip_update.status = 'update'
        st = StopTimeUpdate({'id': 'sa:1'}, departure=_dt("8:15"), arrival=None)
        real_time_update = RealTimeUpdate(raw_data=None, connector='ire')
        trip_update.stop_time_updates.append(st)
        res = handle(real_time_update, [trip_update])

        assert len(res.trip_updates) == 1
        trip_update = res.trip_updates[0]
        assert trip_update.status == 'update'
        assert len(trip_update.stop_time_updates) == 2
        assert trip_update.stop_time_updates[0].stop_id == 'sa:1'
        assert trip_update.stop_time_updates[0].departure == _dt("8:15")
        assert trip_update.stop_time_updates[0].arrival == None

        assert trip_update.stop_time_updates[1].stop_id == 'sa:2'
        assert trip_update.stop_time_updates[1].departure == None
        assert trip_update.stop_time_updates[1].arrival == _dt("9:10")


        # testing that RealTimeUpdate is persisted in db
        db_trip_updates = real_time_update.query.from_self(TripUpdate).all()
        assert len(db_trip_updates) == 1
        assert db_trip_updates[0].status == 'update'
        db_st_updates = real_time_update.query.from_self(StopTimeUpdate).order_by('stop_id').all()
        assert len(db_st_updates) == 2
        assert db_st_updates[0].stop_id == 'sa:1'
        assert db_st_updates[0].departure == _dt("8:15")
        assert db_st_updates[0].arrival == None
        assert db_st_updates[0].trip_update_id == db_trip_updates[0].vj_id

        assert db_st_updates[1].stop_id == 'sa:2'
        assert db_st_updates[1].departure == None
        assert db_st_updates[1].arrival == _dt("9:10")
        assert db_st_updates[1].trip_update_id == db_trip_updates[0].vj_id


def test_handle_new_trip_out_of_order(navitia_vj):
    """
    We have one vj with only one stop time updated, but it's not the first
    so we have to reorder the stop times in the resulting trip_update
    """
    with app.app_context():
        trip_update = TripUpdate()
        vj = VehicleJourney(navitia_vj, datetime.date(2015, 9, 8))
        trip_update.vj = vj
        st = StopTimeUpdate({'id': 'sa:2'}, departure=_dt("9:50"), arrival=_dt("9:49"))
        real_time_update = RealTimeUpdate(raw_data=None, connector='ire')
        trip_update.stop_time_updates.append(st)
        res = handle(real_time_update, [trip_update])

        assert len(res.trip_updates) == 1
        trip_update = res.trip_updates[0]
        assert len(trip_update.stop_time_updates) == 3
        assert trip_update.stop_time_updates[0].stop_id == 'sa:1'
        assert trip_update.stop_time_updates[0].departure == _dt("8:10")
        assert trip_update.stop_time_updates[0].arrival == None

        assert trip_update.stop_time_updates[1].stop_id == 'sa:2'
        assert trip_update.stop_time_updates[1].departure == _dt("9:50")
        assert trip_update.stop_time_updates[1].arrival == _dt("9:49")

        assert trip_update.stop_time_updates[2].stop_id == 'sa:3'
        assert trip_update.stop_time_updates[2].departure == None
        assert trip_update.stop_time_updates[2].arrival == _dt("10:05")


def test_handle_update_vj(setup_database, navitia_vj):
    """
    this time we receive an update for a vj already in the database
    """
    with app.app_context():
        trip_update = TripUpdate()
        vj = VehicleJourney(navitia_vj, datetime.date(2015, 9, 8))
        trip_update.status = 'update'
        trip_update.vj = vj
        st = StopTimeUpdate({'id': 'sa:2'}, departure=_dt("9:20"), arrival=_dt("9:15"))
        st.arrival_status = st.departure_status = 'update'
        real_time_update = RealTimeUpdate(raw_data=None, connector='ire')
        real_time_update.id = '30866ce8-0638-4fa1-8556-1ddfa22d09d3'
        trip_update.stop_time_updates.append(st)
        res = handle(real_time_update, [trip_update])

        assert len(res.trip_updates) == 1
        trip_update = res.trip_updates[0]
        assert trip_update.status == 'update'
        assert len(trip_update.real_time_updates) == 2
        assert len(trip_update.stop_time_updates) == 3

        stu_map = {stu.stop_id: stu for stu in trip_update.stop_time_updates}

        assert 'sa:1' in stu_map
        assert stu_map['sa:1'].arrival == None
        assert stu_map['sa:1'].departure == _dt("8:15")

        assert 'sa:2' in stu_map
        assert stu_map['sa:2'].arrival == _dt("9:15")
        assert stu_map['sa:2'].departure == _dt("9:20")

        assert 'sa:3' in stu_map
        assert stu_map['sa:3'].arrival == _dt("10:05")
        assert stu_map['sa:3'].departure ==  None


        # testing that RealTimeUpdate is persisted in db
        db_trip_updates = TripUpdate.query.join(VehicleJourney).order_by('circulation_date').all()
        assert len(db_trip_updates) == 2
        assert real_time_update.query.from_self(TripUpdate).all()[0].status == 'update'
        st_updates = real_time_update.query.from_self(StopTimeUpdate).order_by('stop_id').all()
        assert len(st_updates) == 6

        # testing that trip update on 2015/09/07 is remaining correctly stored in db
        assert len(db_trip_updates[0].stop_time_updates) == 3
        db_stu_map = {stu.stop_id: stu for stu in db_trip_updates[0].stop_time_updates}

        assert 'sa:1' in db_stu_map
        assert db_stu_map['sa:1'].arrival == None
        assert db_stu_map['sa:1'].departure == _dt("8:35", day=7)

        assert 'sa:2' in db_stu_map
        assert db_stu_map['sa:2'].arrival == _dt("9:35", day=7)
        assert db_stu_map['sa:2'].departure == _dt("9:40", day=7)

        assert 'sa:3' in db_stu_map
        assert db_stu_map['sa:3'].arrival == _dt("10:35", day=7)
        assert db_stu_map['sa:3'].departure ==  None

        # testing that trip update on 2015/09/08 is correctly merged and stored in db
        assert len(db_trip_updates[1].stop_time_updates) == 3
        db_stu_map = {stu.stop_id: stu for stu in db_trip_updates[1].stop_time_updates}

        assert 'sa:1' in db_stu_map
        assert db_stu_map['sa:1'].arrival == None
        assert db_stu_map['sa:1'].departure == _dt("8:15")

        assert 'sa:2' in db_stu_map
        assert db_stu_map['sa:2'].arrival == _dt("9:15")
        assert db_stu_map['sa:2'].departure == _dt("9:20")

        assert 'sa:3' in db_stu_map
        assert db_stu_map['sa:3'].arrival == _dt("10:05")
        assert db_stu_map['sa:3'].departure ==  None
