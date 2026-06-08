import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'payload' / 'scripts'))
import duckdb
from rule_engine_hardening_phase6c import prepare_timeline_context_phase6c, harden_findings_and_segments_phase6c

con=duckdb.connect(':memory:')
# UDF expected by phase6b / phase6c
con.create_function('normalize_company_name', lambda x: ''.join(ch for ch in (x or '').lower() if ch.isalnum()), [str], str)
con.execute('''create table core_loco_timeline(
 run_id varchar,row_type varchar,loco_no varchar,tfze_or_tens varchar,sort_sequence double,movement_sequence_no bigint,
 period_start_utc timestamp,period_end_utc timestamp,sequence_ts timestamp,sequence_ts_source varchar,sequence_ts_reason varchar,
 actual_departure_ts timestamp,actual_arrival_ts timestamp,holder_name varchar,performing_ru varchar,
 cal_start_country varchar,cal_end_country varchar,cal_entry_count_home bigint,cal_exit_count_home bigint,cal_route_type_home varchar,
 performing_ru_marktpartner_id varchar,performing_ru_marktpartner_id_source varchar,holder_market_partner_id varchar,holder_market_partner_id_source varchar,
 user_vens varchar,exempt_vens boolean,exempt_tens boolean,vens_tens_exception_flag boolean,vens_tens_exception_comment varchar,
 country varchar,origin_country_iso varchar,destination_country_iso varchar,clean_dir varchar,faulty_dir varchar,report_scope varchar,de_event_label varchar,
 traction_type varchar,transport_number varchar,train_no varchar,distance varchar,origin_name varchar,destination_name varchar,next_origin_name varchar,next_origin_country_iso varchar,
 gap_from_utc timestamp,gap_to_utc timestamp,gap_duration_minutes bigint,gap_duration_text varchar,gap_message varchar,gap_relevant_de boolean,
 confidence varchar,decision_reason varchar,needs_manual_review boolean,export_ready boolean,dq_severity varchar,dq_message varchar,assignment_reason varchar,
 source_table varchar,source_row_id bigint,display_sequence_no bigint,export_blocking boolean
)''')
# L1: movement DE internal, GAP, movement DE internal; safe 60 min gap
rows=[
('r','MOVEMENT','L1','L1',1,1,'2026-06-06 08:00','2026-06-06 09:00','2026-06-06 08:00','x','x','2026-06-06 08:00','2026-06-06 09:00','Holder A','RU A',None,None,None,None,None,'MP-RU',None,'HOLD-OLD','OLD',None,False,False,False,None,'DE','DE','DE',None,None,'IN_REPORT','In DE',None,'T1',None,None,'A','B','X','DE',None,None,None,None,None,False,None,None,False,True,'','',None,'raw_locomotivemovement',1,1,False),
('r','GAP','L1','L1',1.5,1,'2026-06-06 09:00','2026-06-06 10:00',None,'GAP','gap',None,None,'Holder A',None,None,None,None,None,None,'MP-RU',None,'HOLD-OLD','OLD',None,False,False,False,None,None,'DE','DE',None,None,'GAP','Lücke',None,'T1',None,None,'B','X','X','DE','2026-06-06 09:00','2026-06-06 10:00',60,'60 Minuten','old',True,None,None,False,False,'INFO','old',None,'raw_locomotivemovement',1,2,False),
('r','MOVEMENT','L1','L1',2,2,'2026-06-06 10:00','2026-06-06 11:00','2026-06-06 10:00','x','x','2026-06-06 10:00','2026-06-06 11:00','Holder A','RU A',None,None,None,None,None,'MP-RU',None,'HOLD-OLD','OLD',None,False,False,False,None,'DE','DE','DE',None,None,'IN_REPORT','In DE',None,'T2',None,None,'X','C',None,None,None,None,None,None,None,False,None,None,False,True,'','',None,'raw_locomotivemovement',2,3,False),
# L2 unsafe broken chain (arrival missing) DE internal -> should R015
('r','MOVEMENT','L2','L2',1,1,'2026-06-05 08:00',None,'2026-06-05 08:00','x','x','2026-06-05 08:00',None,'Holder A','RU A',None,None,None,None,None,'MP-RU',None,'HOLD-OLD','OLD',None,False,False,False,None,'DE','DE','DE',None,None,'IN_REPORT','In DE',None,'T3',None,None,'P','Q','R','DE',None,None,None,None,None,False,None,None,False,False,'INFO','missing arr',None,'raw_locomotivemovement',3,1,False),
('r','MOVEMENT','L2','L2',2,2,'2026-06-05 12:00','2026-06-05 13:00','2026-06-05 12:00','x','x','2026-06-05 12:00','2026-06-05 13:00','Holder A','RU A',None,None,None,None,None,'MP-RU',None,'HOLD-OLD','OLD',None,False,False,False,None,'DE','DE','DE',None,None,'IN_REPORT','In DE',None,'T4',None,None,'R','S',None,None,None,None,None,None,None,False,None,None,False,True,'','',None,'raw_locomotivemovement',4,2,False),
# L3 stand candidate same place > 8h
('r','MOVEMENT','L3','L3',1,1,'2026-06-04 00:00','2026-06-04 01:00','2026-06-04 00:00','x','x','2026-06-04 00:00','2026-06-04 01:00','Holder A','RU A',None,None,None,None,None,'MP-RU',None,'HOLD-OLD','OLD',None,False,False,False,None,'DE','DE','DE',None,None,'IN_REPORT','In DE',None,'T5',None,None,'A','Z','Z','DE',None,None,None,None,None,False,None,None,False,True,'','',None,'raw_locomotivemovement',5,1,False),
('r','MOVEMENT','L3','L3',2,2,'2026-06-04 12:00','2026-06-04 13:00','2026-06-04 12:00','x','x','2026-06-04 12:00','2026-06-04 13:00','Holder A','RU A',None,None,None,None,None,'MP-RU',None,'HOLD-OLD','OLD',None,False,False,False,None,'DE','DE','DE',None,None,'IN_REPORT','In DE',None,'T6',None,None,'Z','B',None,None,None,None,None,None,None,False,None,None,False,True,'','',None,'raw_locomotivemovement',6,2,False),
]
# easier placeholders
placeholders=','.join(['?']*len(rows[0]))
con.executemany('insert into core_loco_timeline values ('+placeholders+')',rows)
con.execute("create table dq_run_metadata(run_id varchar,source_snapshot_at_utc timestamp,error_cutoff_utc timestamp,calculated_at_utc timestamp)")
con.execute("insert into dq_run_metadata values ('r','2026-06-08 12:00','2026-06-07 12:00','2026-06-08 12:00')")
con.execute("create table dq_findings(run_id varchar,severity varchar,rule_id varchar,rule_group varchar,loco_no varchar,transport_number varchar,performing_ru varchar,row_type varchar,movement_sequence_no bigint,period_start_utc timestamp,period_end_utc timestamp,message varchar,suggested_action varchar,status varchar,source_table varchar,source_row_id bigint,overlap_with_transport_number varchar)")
con.execute("insert into dq_findings values ('r','INFO','R010.5','TIMELINE','L1','T1',null,'GAP',1,'2026-06-06 09:00','2026-06-06 10:00','old','old','info','raw_locomotivemovement',1,null)")
con.execute("create table cfg_dq_rule_catalog(rule_id varchar,rule_group varchar,severity_policy varchar,description varchar,active boolean)")
con.execute("create table cfg_market_partner_mapping_effective(role_code varchar,source_value_normalized varchar,market_partner_id varchar)")
con.execute("create table cfg_market_partner_role_effective(role_code varchar,company_name_normalized varchar,market_partner_id varchar)")
con.execute("create table raw_transportdetail(TransportNumber varchar,FirstLocomotiveNo varchar,MovementType varchar,ActualDeparture varchar,OriginCountryISO varchar,DestinationCountryISO varchar)")
con.execute("insert into raw_transportdetail values ('TD1','00000000000-0','Train movement','2026-06-01 01:00','DE','DE')")
con.execute("create table cfg_excluded_cancelled_transports(transport_number varchar)")
prepare_timeline_context_phase6c(con,'r')
harden_findings_and_segments_phase6c(con,'r')
print('segments',con.execute('select loco_no,usage_segment_id,segment_start_utc,segment_end_utc from core_usage_assignment_segments order by 1,2').fetchall())
print('stands',con.execute('select loco_no,stand_duration_minutes from core_loco_stand_candidates').fetchall())
print('uncertain',con.execute('select loco_no from dq_phase6c_uncertain_gaps').fetchall())
print('findings',con.execute("select rule_id,loco_no,transport_number,severity from dq_findings order by rule_id,loco_no").fetchall())
assert con.execute("select count(*) from dq_findings where rule_id='R015' and loco_no='L2'").fetchone()[0]==1
assert con.execute("select count(*) from dq_findings where rule_id='R012' and transport_number='TD1'").fetchone()[0]==1
assert con.execute("select count(*) from core_loco_stand_candidates where loco_no='L3'").fetchone()[0]==1
assert con.execute("select count(*) from core_usage_assignment_segments").fetchone()[0]>=3
print('OK')
