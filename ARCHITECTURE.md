# Refatoração arquitetural aplicada

Este projeto foi refatorado de forma incremental para um monólito Django mais modular, mantendo compatibilidade com URLs, templates e migrations existentes.

## Camadas introduzidas

### `appointments/availability.py`
Centraliza regras de disponibilidade:

- horário de funcionamento;
- bloqueios pontuais e recorrentes;
- conflito entre marcações;
- geração de horários públicos disponíveis;
- construção da agenda visual.

### `appointments/selectors.py`
Centraliza queries de leitura usadas por views:

- listagem filtrada de marcações;
- marcações por cliente;
- agenda diária;
- bloqueios por data.

### `appointments/use_cases.py`
Centraliza casos de uso transacionais:

- confirmação de marcação;
- conclusão de marcação.

## Modelos

`Appointment.clean()` deixou de conter a regra completa de disponibilidade e passou a delegar para `AvailabilityService.validate_appointment()`. Isto mantém a validação automática via `full_clean()`, mas tira complexidade do model.

## Views

As views foram reduzidas para responsabilidades de apresentação/orquestração:

- `AppointmentListView` usa `AppointmentSelectors` e `AppointmentFilters`;
- `CustomerAppointmentsView` e `CustomerAppointmentDetailView` usam selectors;
- `PublicBookingAvailabilityMixin` usa `AvailabilityService`;
- `VisualScheduleView` usa `AvailabilityService.build_visual_slots()`;
- confirmação/conclusão usam use cases transacionais.

## Banco de dados

Foi adicionada a migration `0002_architecture_indexes.py` com índices para consultas frequentes:

- data/hora de marcação;
- status/data;
- cliente/data;
- bloqueios por data/hora.

## Próximos passos recomendados

1. Extrair `customers`, `services_catalog`, `notifications` e `audit` para apps independentes.
2. Transformar criação/cancelamento em use cases formais também.
3. Dividir `appointments/tests/tests.py` por caso de uso.
4. Separar `config/settings.py` em `base.py`, `dev.py`, `prod.py`.
5. Adicionar Celery/Redis para emails e lembretes assíncronos.
