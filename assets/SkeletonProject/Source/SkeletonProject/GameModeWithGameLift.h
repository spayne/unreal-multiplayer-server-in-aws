// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameModeWithGameLift.generated.h"

DECLARE_LOG_CATEGORY_EXTERN(LogGameLift, Log, All);

UCLASS(minimalapi)
class AGameModeWithGameLift: public AGameModeBase
{
	GENERATED_BODY()

public:
	AGameModeWithGameLift();

private:
	void SetupGameLift();
};



