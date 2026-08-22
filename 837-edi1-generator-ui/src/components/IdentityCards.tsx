/**
 * Section 04. Shared once across the whole batch, never per claim.
 *
 * The fields shown are the ones the generator can actually honour
 * (generate.py's _IDENTITY_SEGMENTS): subscriber last/first/memberId/dob,
 * the billing provider's name and NPI, the attending provider when the seed
 * carries one, and the tax ID when it carries a REF*EI. Offering a field the
 * generator would ignore is worse than not offering it.
 */
import type { Identity, IdentityGroup, TxType } from '@/api/types';
import { parseDate, showDate } from '@/lib/fields';

interface FieldSpec {
  group: IdentityGroup;
  field: string;
  label: string;
  date?: boolean;
}

function subscriberFields(): FieldSpec[] {
  return [
    { group: 'subscriber', field: 'memberId', label: 'Member ID' },
    { group: 'subscriber', field: 'last', label: 'Last Name' },
    { group: 'subscriber', field: 'first', label: 'First Name' },
    { group: 'subscriber', field: 'dob', label: 'Date of Birth', date: true },
  ];
}

function providerFields(identity: Identity, type: TxType): FieldSpec[] {
  const out: FieldSpec[] = [
    {
      group: 'billingProvider',
      field: 'npi',
      label: type === 'I' ? 'Billing Facility NPI' : 'Billing Provider NPI',
    },
    {
      group: 'billingProvider',
      field: 'name',
      label: type === 'I' ? 'Facility Name' : 'Provider Name',
    },
  ];
  if (identity.attendingProvider) {
    out.push(
      { group: 'attendingProvider', field: 'npi',
        label: 'Attending Physician NPI' },
      { group: 'attendingProvider', field: 'last',
        label: 'Attending Last Name' },
      { group: 'attendingProvider', field: 'first',
        label: 'Attending First Name' },
    );
  }
  if (identity.taxId != null) {
    out.push({ group: 'taxId', field: 'taxId', label: 'Tax ID' });
  }
  return out;
}

function read(identity: Identity, spec: FieldSpec): string {
  if (spec.group === 'taxId') return identity.taxId ?? '';
  const group = identity[spec.group] as unknown as
    Record<string, string> | undefined;
  return group?.[spec.field] ?? '';
}

function Card({ title, autoFilled, fields, identity, onChange }: {
  title: string;
  autoFilled: boolean;
  fields: FieldSpec[];
  identity: Identity;
  onChange: (g: IdentityGroup, f: string, v: string) => void;
}) {
  return (
    <div className="panel">
      <div className="panel__head">
        <div className="panel__title">{title}</div>
        {autoFilled && <div className="tag-auto">Auto-filled</div>}
      </div>
      <div className="panel__body">
        {fields.map((spec) => {
          const id = `${spec.group}-${spec.field}`;
          const value = read(identity, spec);
          return (
            <div className="field" key={id}>
              <label htmlFor={id}>{spec.label}</label>
              <input
                id={id}
                type="text"
                value={spec.date ? showDate(value) : value}
                placeholder={spec.date ? 'MM/DD/YYYY' : undefined}
                onChange={(e) => onChange(spec.group, spec.field,
                  spec.date ? parseDate(e.target.value) : e.target.value)}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function IdentityCards({ identity, type, editedGroups, onChange }: {
  identity: Identity;
  type: TxType;
  editedGroups: Set<string>;
  onChange: (g: IdentityGroup, f: string, v: string) => void;
}) {
  const providerGroups = ['billingProvider', 'attendingProvider', 'taxId'];
  return (
    <div className="panels">
      <Card
        title="Subscriber / Member Info"
        autoFilled={!editedGroups.has('subscriber')}
        fields={subscriberFields()}
        identity={identity}
        onChange={onChange}
      />
      <Card
        title="Provider Info"
        autoFilled={!providerGroups.some((g) => editedGroups.has(g))}
        fields={providerFields(identity, type)}
        identity={identity}
        onChange={onChange}
      />
    </div>
  );
}
