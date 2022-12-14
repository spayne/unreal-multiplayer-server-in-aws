// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Http.h"
#include "OfflineMainMenuWidget.generated.h"

/**
 * 
 */
UCLASS()
class MYPROJECT_API UOfflineMainMenuWidget : public UUserWidget
{
	GENERATED_BODY()
	
public:
	UOfflineMainMenuWidget(const FObjectInitializer& ObjectInitializer);

	UFUNCTION(BlueprintCallable)
	void OnLoginClicked();

	UPROPERTY(EditAnywhere)
	FString ApiGatewayEndpoint;

	UPROPERTY(EditAnywhere)
	FString LoginURI;

	UPROPERTY(EditAnywhere)
	FString StartSessionURI;

	UPROPERTY(BluePrintReadWrite)
	FString user;

	UPROPERTY(BluePrintReadWrite)
	FString pass;

private:
	FHttpModule* Http;
	void LoginRequest(FString usr, FString pwd);
	void OnLoginResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful);
	void StartSessionRequest(FString idt);
	void OnStartSessionResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful);



};
