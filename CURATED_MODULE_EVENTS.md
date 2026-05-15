# Curated Module Sentinel Events

This document mirrors the Curated Module event catalog from
`sentinel/modules/curated/adapter.py` and the notification copy from
`sentinel/modules/curated/texts.py`.

## Current Event Catalog

The Curated Module currently follows 46 events.

### CuratedModule

- `DepositedSigningKeysCountChanged`
- `TotalSigningKeysCountChanged`
- `VettedSigningKeysCountDecreased`
- `KeyRemovalChargeApplied`
- `KeyAllocatedBalanceChanged`
- `TargetValidatorsCountChanged`
- `NodeOperatorManagerAddressChangeProposed`
- `NodeOperatorManagerAddressChanged`
- `NodeOperatorRewardAddressChangeProposed`
- `NodeOperatorRewardAddressChanged`
- `GeneralDelayedPenaltyReported`
- `GeneralDelayedPenaltySettled`
- `GeneralDelayedPenaltyCancelled`
- `GeneralDelayedPenaltyCompensated`
- `ValidatorSlashingReported`
- `ValidatorWithdrawn`
- `Initialized`

### CSAccounting

- `BondCurveSet`
- `CustomRewardsClaimerSet`
- `FeeSplitsSet`
- `BondDebtIncreased`
- `BondDebtCovered`
- `ExpiredBondLockRemoved`
- `BondDepositedETH`
- `BondDepositedStETH`
- `BondDepositedWstETH`
- `BondClaimedUnstETH`
- `BondClaimedStETH`
- `BondClaimedWstETH`
- `BondBurned`
- `BondCharged`
- `BondLockChanged`
- `BondLockRemoved`
- `BondLockCompensated`
- `BondLockPeriodChanged`

### CSExitPenalties

- `ValidatorExitDelayProcessed`
- `TriggeredExitFeeRecorded`
- `StrikesPenaltyProcessed`

### CSFeeDistributor

- `DistributionLogUpdated`

### ValidatorsExitBusOracle

- `ValidatorExitRequest`

### MetaRegistry

- `NodeOperatorEffectiveWeightChanged`
- `OperatorGroupCreated`
- `OperatorGroupUpdated`
- `OperatorGroupCleared`
- `BondCurveWeightSet`
- `OperatorMetadataSet`

## Event List Shown In The Bot

### Key Management Events

Changes related to keys, limits, and operator type.

- 🤩 Node Operator's keys received deposits
- 👀 New keys uploaded or removed
- 🚨 Uploaded invalid or duplicated keys
- 🔑 Applied charge for key removal
- 👀 Key allocated bond balance changed
- ℹ️ Node Operator type changed
- 🚨 Target validators count changed

### Address and Reward Changes

Changes or proposals for management and reward configuration.

- ℹ️ New manager address proposed
- ✅ Manager address changed
- ℹ️ New rewards address proposed
- ✅ Rewards address changed
- ℹ️ Custom rewards claimer changed
- ℹ️ Reward fee splits changed

### Bond Events

Changes to deposited, claimed, locked, burned, or charged bond.

- ✅ ETH bond deposited
- ✅ stETH bond deposited
- ✅ wstETH bond deposited
- ✅ unstETH bond claim requested
- ✅ stETH bond claimed
- ✅ wstETH bond claimed
- 🚨 Bond burned
- 🚨 Bond charged
- 🚨 Bond lock changed
- ✅ Bond lock removed
- ✅ Bond lock compensated
- ℹ️ Bond lock period changed

### Penalty Events

Alerts for delayed penalties, slashing, debt, and strikes.

- 🚨 General delayed penalty reported
- 🚨 General delayed penalty confirmed and applied
- 😮‍💨 Cancelled general delayed penalty
- ✅ General delayed penalty compensated
- 🚨 Validator slashing reported
- 🚨 Bond debt increased
- ✅ Bond debt covered
- ✅ Expired bond lock removed
- 🚨 Strikes penalty processed

### Withdrawal and Exit Requests

Notifications for exit requests and confirmed withdrawals.

- 🚨 One of the validators requested to exit
- 🚨 Validator exit delay penalty issued
- 🚨 Triggerable Withdrawal fee recorded
- 👀 Validator withdrawal confirmed

### Operator Group Events

Changes from the Curated Module MetaRegistry.

- ℹ️ Operator effective weight changed
- ℹ️ Operator group created
- ℹ️ Operator group updated
- 🚨 Operator group cleared
- ℹ️ Operator type weight changed
- ℹ️ Operator metadata changed

### Common Curated Module Events

- 📈 New rewards distributed
- 🎉 Curated Module launched

## Message Templates

Templates below show the rendered Telegram message text. Bold, code, and links
are applied by Telegram formatting; link labels are shown as text.

Footer blocks are rendered inline in the templates below.

Operator footer with a MetaRegistry name:

```text
Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

Operator footer when the name cannot be fetched or is empty:

```text
nodeOperatorId: {nodeOperatorId}
Transaction: {tx_url}
```

Transaction-only footer:

```text
Transaction: {tx_url}
```

In the bot UI, `Transaction` is rendered as a link label pointing to `{tx_url}`.

### Core Curated Module Events

### `DepositedSigningKeysCountChanged`

```text
🤩 Keys were deposited!

New deposited keys count: {depositedKeysCount}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `TotalSigningKeysCountChanged`

When count increased:

```text
👀 New keys uploaded

Keys count: {oldTotalKeysCount} -> {totalKeysCount}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When count decreased:

```text
🚨 Key removed

Total keys: {totalKeysCount}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `VettedSigningKeysCountDecreased`

```text
🚨 Vetted keys count decreased

Invalid or duplicated keys has been uploaded.
Remove the keys on the Curated Module UI.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `KeyRemovalChargeApplied`

```text
🔑 Key removal charge applied

Amount of charge: {amount}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `KeyAllocatedBalanceChanged`

```text
👀 Key balance increased

Key index: {keyIndex}
New allocated balance: {newTotal}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondCurveSet`

```text
ℹ️ Operator type changed

New type id: {curveId}
Operational requirements may now differ. Check the Curated Module UI for updated guidance.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `TargetValidatorsCountChanged`

When mode is soft and the limit is set to zero:

```text
🚨 Target validators count changed

The limit has been set to zero.
All keys will be requested to exit first.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When mode is forced and the limit is set to zero:

```text
🚨 Target validators count changed

The limit has been set to zero.
All keys will be requested to exit immediately.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When the soft limit is decreased:

```text
🚨 Target validators count changed

The limit has been decreased from {limitBefore} to {limitAfter}.
{decreasedBy} more key(s) will be requested to exit first.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When the forced limit is decreased:

```text
🚨 Target validators count changed

The limit has been decreased from {limitBefore} to {limitAfter}.
{decreasedBy} more key(s) will be requested to exit immediately.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When mode is set to soft:

```text
🚨 Target validators count changed

The limit has been set to {limitAfter}.
{limitAfter} keys will be requested to exit first.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When mode is set to forced:

```text
🚨 Target validators count changed

The limit has been set to {limitAfter}.
{limitAfter} keys will be requested to exit immediately.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When target mode is disabled:

```text
🚨 Target validators count changed

The limit has been set to zero. No keys will be requested to exit.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

Otherwise:

```text
🚨 Target validators count changed

Mode changed from {modeBefore} to {modeAfter}.
Limit changed from {limitBefore} to {limitAfter}.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `NodeOperatorManagerAddressChangeProposed`

When proposed address is zero:

```text
ℹ️ Proposed manager address revoked

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

Otherwise:

```text
ℹ️ New manager address proposed

Proposed address: {newProposedAddress}
To complete the change, the Node Operator must confirm it from the new address.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `NodeOperatorManagerAddressChanged`

```text
✅ Manager address changed

New address: {newAddress}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `NodeOperatorRewardAddressChangeProposed`

When proposed address is zero:

```text
ℹ️ Proposed reward address revoked

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

Otherwise:

```text
ℹ️ New rewards address proposed

Proposed address: {newProposedAddress}
To complete the change, the Node Operator must confirm it from the new address.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `NodeOperatorRewardAddressChanged`

```text
✅ Rewards address changed

New address: {newAddress}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `CustomRewardsClaimerSet`

When claimer is zero:

```text
ℹ️ Custom rewards claimer removed

Custom rewards claimer was removed for this Node Operator.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When claimer is set from zero to a non-zero address:

```text
ℹ️ Custom rewards claimer set

Rewards claimer: {rewardsClaimer}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When claimer is changed from one non-zero address to another:

```text
ℹ️ Custom rewards claimer changed

Rewards claimer: {rewardsClaimer}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `FeeSplitsSet`

```text
ℹ️ Fee splits changed

Fee splits: {recipient1}: {share1}; {recipient2}: {share2}
Review the current rewards setup in the Curated Module UI.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondDebtIncreased`

```text
🚨 Bond debt increased

Debt increase: {amount}

Future rewards or bond changes may be used to cover this debt.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondDebtCovered`

```text
✅ Bond debt covered

Covered amount: {amount}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `ExpiredBondLockRemoved`

```text
✅ Expired bond lock removed

More bond may now be available for normal operations.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `GeneralDelayedPenaltyReported`

```text
🚨 General delayed penalty reported

Penalty amount: {amount}
Additional fine: {additionalFine}
Details: {details}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `GeneralDelayedPenaltySettled`

```text
🚨 General delayed penalty confirmed and applied

Settled amount: {amount}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `GeneralDelayedPenaltyCancelled`

```text
😮‍💨 General delayed penalty cancelled

Remaining amount: {remaining}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `GeneralDelayedPenaltyCompensated`

```text
✅ General delayed penalty compensated

Compensated amount: {amount}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `ValidatorSlashingReported`

```text
🚨 Validator slashing reported

Validator: {pubkey_link}
Key index: {keyIndex}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `ValidatorExitRequest`

`exitUntil` is calculated as `requestDate + allowedExitDelay`, where
`allowedExitDelay` is read from the Node Operator's current bond curve
parameters at the event block.

```text
🚨 Validator exit requested

Make sure to exit the key before {exitUntil}
Requested key: {pubkey_link}
Request date: {requestDate}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `ValidatorExitDelayProcessed`

```text
🚨 Validator exit delay penalty issued

Validator: {pubkey_link}
Delay penalty: {delayFee}

Penalty will be applied when the validator exits.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `TriggeredExitFeeRecorded`

```text
🚨 Triggerable Withdrawal fee recorded

Validator: {pubkey_link}
Fee to be charged on exit: {withdrawalRequestRecordedFee}

Exit fee will be applied when the validator exits.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `StrikesPenaltyProcessed`

```text
🚨 Strikes penalty processed

Validator: {pubkey_link}
Penalty amount: {strikesPenalty}

Penalty will be charged when the validator withdraws.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `ValidatorWithdrawn`

```text
👀 Validator withdrawal confirmed

Withdrawn key: {pubkey_link}
Exit balance: {exitBalance}
Slashing penalty: {slashingPenalty}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

Omit the slashing penalty line when it is zero.

### `DistributionLogUpdated`

Base broadcast:

```text
📈 Rewards distributed!

Follow the Curated Module UI to check new claimable rewards.

Transaction: {tx_url}
```

When strikes are present:

```text
📈 Rewards distributed!

Follow the Curated Module UI to check new claimable rewards.

⚠️ Strikes detected for validators
Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Validators with strikes: {count}

Transaction: {tx_url}
```

When a Node Operator name is unavailable, the strike message falls back to
`Node Operator: #{nodeOperatorId}`.

### `Initialized`

```text
🎉 Curated Module is live!

Check the Curated Module UI for operator workflows and current module details.

Transaction: {tx_url}
```

### Bond Events

### `BondDepositedETH`

```text
✅ Bond deposited

From: {from}
Amount: {amount} ETH

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondDepositedStETH`

```text
✅ Bond deposited

From: {from}
Amount: {amount} stETH

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondDepositedWstETH`

```text
✅ Bond deposited

From: {from}
Amount: {amount} wstETH

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondClaimedUnstETH`

```text
✅ Bond claim requested

Recipient: {to}
Amount: {amount} unstETH
Withdrawal request id: {requestId}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondClaimedStETH`

```text
✅ Bond claimed

Recipient: {to}
Amount: {amount} stETH

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondClaimedWstETH`

```text
✅ Bond claimed

Recipient: {to}
Amount: {amount} wstETH

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondBurned`

```text
🚨 Bond burned

Burned amount: {burnedAmount} ETH

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondCharged`

```text
🚨 Bond charged

Requested charge: {amountToCharge} ETH
Charged amount: {chargedAmount} ETH

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondLockChanged`

```text
🚨 Bond lock changed

Locked amount: {newAmount} ETH
Locked until: {until}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondLockRemoved`

```text
✅ Bond lock removed

Previously locked bond is no longer retained.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondLockCompensated`

```text
✅ Bond lock compensated

Compensated amount: {amount} ETH

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `BondLockPeriodChanged`

```text
ℹ️ Bond lock period changed

New period: {period}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `NodeOperatorEffectiveWeightChanged`

When new weight is zero:

```text
🚨 Operator effective weight changed

Effective weight: {oldWeight} -> 0

The Node Operator may no longer receive deposit allocation until weight is restored.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

Otherwise:

```text
ℹ️ Operator effective weight changed

Effective weight: {oldWeight} -> {newWeight}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `OperatorGroupCreated`

```text
ℹ️ Operator group created

Group id: {groupId}
Added Node Operators:
- #{nodeOperatorId} - {name}: share {share}
- #{nodeOperatorId} - {name}: share {share}

Transaction: {tx_url}
```

When a Node Operator name is unavailable, the list falls back to `#{nodeOperatorId}`.

### `OperatorGroupUpdated`

When Node Operator is added:

```text
ℹ️ Operator group updated

Group id: {groupId}

Node Operator: #{nodeOperatorId} - {name}
Node Operator added with share: {share}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When Node Operator remains but share changed:

```text
ℹ️ Operator group updated

Group id: {groupId}

Node Operator: #{nodeOperatorId} - {name}
Node Operator share changed: {oldShare} -> {newShare}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When Node Operator is removed:

```text
🚨 Operator group updated

Group id: {groupId}

Node Operator: #{nodeOperatorId} - {name}
Node Operator removed from this group.

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

When a Node Operator name is unavailable, the label falls back to `#{nodeOperatorId}`.

### `OperatorGroupCleared`

```text
🚨 Operator group cleared

Group id: {groupId}
Affected Node Operators:
- #{nodeOperatorId} - {name}: share {share}
- #{nodeOperatorId} - {name}: share {share}

Transaction: {tx_url}
```

When a Node Operator name is unavailable, the affected list falls back to
`#{nodeOperatorId}`.

### `BondCurveWeightSet`

No notification is sent when no Node Operators currently use the updated bond
curve.

```text
ℹ️ Operator type weight changed

Type id: {curveId}
New weight: {weight}

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

### `OperatorMetadataSet`

```text
ℹ️ Operator metadata changed

Name: {metadata.name}
Description: {metadata.description}
Owner edits restricted: true

Node Operator: #{nodeOperatorId} - {nodeOperatorName}
Transaction: {tx_url}
```

Omit the owner edits restricted line unless `metadata.ownerEditsRestricted` is true.
