# Curated Module Sentinel Events

## Existing Events Inherited From CSM

### `DepositedSigningKeysCountChanged`

```text
🤩 Keys were deposited!
New deposited keys count: {depositedKeysCount}
```

### `TotalSigningKeysCountChanged`

When count increased:

```text
👀 New keys uploaded
Keys count: {oldTotalKeysCount} -> {totalKeysCount}
```

When count decreased:

```text
🚨 Key removed
Total keys: {totalKeysCount}
```

### `VettedSigningKeysCountDecreased`

```text
🚨 Vetted keys count decreased
Invalid or duplicated keys has been uploaded.
Remove the keys on the Curated Module UI.
```

### `KeyRemovalChargeApplied`

```text
🔑 Key removal charge applied
Amount of charge: {amount}
```

### `KeyAllocatedBalanceChanged`

```text
👀 Key allocated balance changed
Key index: {keyIndex}
New allocated balance: {newTotal}
```

### `BondCurveSet`

```text
ℹ️ Operator type changed
New type id: {curveId}
Operational requirements may now differ. Check the Curated Module UI for updated guidance.
```

### `TargetValidatorsCountChanged`

When mode is soft and the limit is set to zero:

```text
🚨 Target validators count changed
The limit has been set to zero.
All keys will be requested to exit first.
```

When mode is forced and the limit is set to zero:

```text
🚨 Target validators count changed
The limit has been set to zero.
All keys will be requested to exit immediately.
```

When the soft limit is decreased:

```text
🚨 Target validators count changed
The limit has been decreased from {limitBefore} to {limitAfter}.
{decreasedBy} more key(s) will be requested to exit first.
```

When the forced limit is decreased:

```text
🚨 Target validators count changed
The limit has been decreased from {limitBefore} to {limitAfter}.
{decreasedBy} more key(s) will be requested to exit immediately.
```

When mode is set to soft:

```text
🚨 Target validators count changed
The limit has been set to {limitAfter}.
{limitAfter} keys will be requested to exit first.
```

When mode is set to forced:

```text
🚨 Target validators count changed
The limit has been set to {limitAfter}.
{limitAfter} keys will be requested to exit immediately.
```

When target mode is disabled:

```text
🚨 Target validators count changed
The limit has been set to zero. No keys will be requested to exit.
```

Otherwise:

```text
🚨 Target validators count changed
Mode changed from {modeBefore} to {modeAfter}.
Limit changed from {limitBefore} to {limitAfter}.
```

### `NodeOperatorManagerAddressChangeProposed`

When proposed address is zero:

```text
ℹ️ Proposed manager address revoked
```

Otherwise:

```text
ℹ️ New manager address proposed
Proposed address: {newProposedAddress}
To complete the change, the operator must confirm it from the new address.
```

### `NodeOperatorManagerAddressChanged`

```text
✅ Manager address changed
New address: {newAddress}
```

### `NodeOperatorRewardAddressChangeProposed`

When proposed address is zero:

```text
ℹ️ Proposed reward address revoked
```

Otherwise:

```text
ℹ️ New rewards address proposed
Proposed address: {newProposedAddress}
To complete the change, the operator must confirm it from the new address.
```

### `NodeOperatorRewardAddressChanged`

```text
✅ Rewards address changed
New address: {newAddress}
```

### `CustomRewardsClaimerSet`

When claimer is zero:

```text
ℹ️ Custom rewards claimer removed
Custom rewards claimer was removed for this operator.
```

When claimer is set from zero to a non-zero address:

```text
ℹ️ Custom rewards claimer set
Rewards claimer: {rewardsClaimer}
```

When claimer is changed from one non-zero address to another:

```text
ℹ️ Custom rewards claimer changed
Rewards claimer: {rewardsClaimer}
```

### `FeeSplitsSet`

```text
ℹ️ Fee splits changed
Fee splits: {recipient1}: {share1}; {recipient2}: {share2}
Review the current rewards setup in the Curated Module UI.
```

### `BondDebtIncreased`

```text
🚨 Bond debt increased
Debt increase: {amount}
Future rewards or bond changes may be used to cover this debt.
```

### `BondDebtCovered`

```text
✅ Bond debt covered
Covered amount: {amount}
```

### `ExpiredBondLockRemoved`

```text
✅ Expired bond lock removed
More bond may now be available for normal operations.
```

### `GeneralDelayedPenaltyReported`

```text
🚨 General delayed penalty reported
Penalty amount: {amount}
Additional fine: {additionalFine}
Details: {details}
```

### `GeneralDelayedPenaltySettled`

```text
🚨 General delayed penalty confirmed and applied
Settled amount: {amount}
```

### `GeneralDelayedPenaltyCancelled`

```text
😮‍💨 General delayed penalty cancelled
Remaining amount: {remaining}
```

### `GeneralDelayedPenaltyCompensated`

```text
✅ General delayed penalty compensated
Compensated amount: {amount}
```

### `ValidatorSlashingReported`

```text
🚨 Validator slashing reported
Validator: {pubkey_link}
Key index: {keyIndex}
```

### `ValidatorExitRequest`

```text
🚨 Validator exit requested
Make sure to exit the key before {exitUntil}.
Requested key: {pubkey_link}
Request date: {requestDate}
```

### `ValidatorExitDelayProcessed`

```text
🚨 Validator exit delay penalty issued
Validator: {pubkey_link}
Delay penalty: {delayFee}
Penalty will be applied when the validator exits.
```

### `TriggeredExitFeeRecorded`

```text
🚨 Triggerable Withdrawal fee recorded
Validator: {pubkey_link}
Fee paid now: {withdrawalRequestPaidFee}
Fee to be charged on exit: {withdrawalRequestRecordedFee}
Exit fee will be applied when the validator exits.
```

### `StrikesPenaltyProcessed`

```text
🚨 Strikes penalty processed
Validator: {pubkey_link}
Penalty amount: {strikesPenalty}
Penalty will be charged when the validator withdraws.
```

### `ValidatorWithdrawn`

```text
👀 Validator withdrawal confirmed
Withdrawn key: {pubkey_link}
Exit balance: {exitBalance}
Slashing penalty: {slashingPenalty}
```

Omit the slashing penalty line when it is zero.

### `DistributionLogUpdated`

Base broadcast:

```text
📈 Rewards distributed!
Follow the Curated Module UI to check new claimable rewards.
```

When strikes are present:

```text
⚠️ Strikes detected for validators
Operator ID: {nodeOperatorId}
Validators with strikes: {count}
```

### `Initialized`

```text
🎉 Curated Module is live!
Check the Curated Module UI for operator workflows and current module details.
```

## New Events For Curated

### `BondDepositedETH`

```text
✅ Bond deposited
Asset: ETH
From: {from}
Amount: {amount}
```

### `BondDepositedStETH`

```text
✅ Bond deposited
Asset: stETH
From: {from}
Amount: {amount}
```

### `BondDepositedWstETH`

```text
✅ Bond deposited
Asset: wstETH
From: {from}
Amount: {amount}
```

### `BondClaimedUnstETH`

```text
✅ Bond claim requested
Asset: unstETH
Recipient: {to}
Amount: {amount}
Withdrawal request id: {requestId}
```

### `BondClaimedStETH`

```text
✅ Bond claimed
Asset: stETH
Recipient: {to}
Amount: {amount}
```

### `BondClaimedWstETH`

```text
✅ Bond claimed
Asset: wstETH
Recipient: {to}
Amount: {amount}
```

### `BondBurned`

```text
🚨 Bond burned
Burned amount: {burnedAmount}
```

### `BondCharged`

```text
🚨 Bond charged
Requested charge: {amountToCharge}
Charged amount: {chargedAmount}
```

### `BondLockChanged`

```text
🚨 Bond lock changed
Locked amount: {newAmount}
Locked until: {until}
```

### `BondLockRemoved`

```text
✅ Bond lock removed
Previously locked bond is no longer retained.
```

### `BondLockCompensated`

```text
✅ Bond lock compensated
Compensated amount: {amount}
```

### `BondLockPeriodChanged`

```text
ℹ️ Bond lock period changed
New period: {period}
```

### `NodeOperatorEffectiveWeightChanged`

When new weight is zero:

```text
🚨 Operator effective weight changed
Effective weight: {oldWeight} -> 0
The Node Operator may no longer receive deposit allocation until weight is restored.
```

Otherwise:

```text
ℹ️ Operator effective weight changed
Effective weight: {oldWeight} -> {newWeight}
```

### `OperatorGroupCreated`

```text
ℹ️ Operator group created
Group id: {groupId}
Added Node Operators:
- #{nodeOperatorId}: share {share}
- #{nodeOperatorId}: share {share}
```

### `OperatorGroupUpdated`

When Node Operator is added:

```text
ℹ️ Operator group updated
Group id: {groupId}
Node Operator added with share: {share}
```

When Node Operator remains but share changed:

```text
ℹ️ Operator group updated
Group id: {groupId}
Node Operator share changed: {oldShare} -> {newShare}
```

When Node Operator is removed:

```text
🚨 Operator group updated
Group id: {groupId}
Node Operator removed from this group.
```

### `OperatorGroupCleared`

```text
🚨 Operator group cleared
Group id: {groupId}
Node Operator removed from the cleared group.
```

### `BondCurveWeightSet`

Global:

```text
ℹ️ Operator type weight changed
Type id: {curveId}
New weight: {weight}
```

When mapped to a Node Operator:

```text
ℹ️ Operator type weight changed
Node Operator uses type id: {curveId}
New type weight: {weight}
```

### `OperatorMetadataSet`

```text
ℹ️ Operator metadata changed
Name: {metadata.name}
Description: {metadata.description}
```

Include this line only when owner edits are explicitly restricted:

```text
Owner edits restricted: true
```
