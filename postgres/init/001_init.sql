create table if not exists users (
  id bigserial primary key,
  name varchar(100) not null,
  channel_user_id varchar(100),
  role varchar(50),
  status varchar(20) default 'active',
  created_at timestamptz default now()
);

create table if not exists suppliers (
  id bigserial primary key,
  name varchar(200) not null unique,
  alias varchar(200),
  status varchar(20) default 'active',
  created_at timestamptz default now()
);

create table if not exists products (
  id bigserial primary key,
  name varchar(200) not null unique,
  alias varchar(200),
  default_unit varchar(50),
  status varchar(20) default 'active',
  created_at timestamptz default now()
);

create table if not exists purchase_requests (
  id bigserial primary key,
  request_no varchar(50) not null unique,
  requester_id bigint references users(id),
  supplier_id bigint references suppliers(id),
  purchase_date date,
  status varchar(30) not null default 'draft',
  source_channel varchar(50),
  raw_text text,
  confirmed_at timestamptz,
  created_at timestamptz default now()
);

create table if not exists purchase_request_items (
  id bigserial primary key,
  purchase_request_id bigint not null references purchase_requests(id) on delete cascade,
  product_id bigint references products(id),
  product_name_snapshot varchar(200) not null,
  qty numeric(18,4) not null,
  unit varchar(50) not null,
  remark text,
  created_at timestamptz default now()
);

create table if not exists event_logs (
  id bigserial primary key,
  entity_type varchar(50) not null,
  entity_id bigint,
  event_type varchar(50) not null,
  operator varchar(100),
  raw_payload jsonb,
  created_at timestamptz default now()
);

insert into users (name, channel_user_id, role)
values ('果栋', 'demo_user_001', 'requester');

insert into suppliers (name, alias)
values ('采无忧', '采无忧供应')
on conflict (name) do nothing;

insert into products (name, alias, default_unit)
values
  ('五常大米', '大米', '斤'),
  ('嘉木东来寿眉白茶', '寿眉白茶', '盒'),
  ('萌考拉冰淇淋', '冰淇淋', '个')
on conflict (name) do nothing;