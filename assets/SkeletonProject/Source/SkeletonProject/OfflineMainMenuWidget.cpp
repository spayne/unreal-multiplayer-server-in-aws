// Fill out your copyright notice in the Description page of Project Settings.


#include "OfflineMainMenuWidget.h"
#include "Json.h"
#include "JsonUtilities.h"
#include "Kismet/GameplayStatics.h"


UOfflineMainMenuWidget::UOfflineMainMenuWidget(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	Http = &FHttpModule::Get();

	ApiGatewayEndpoint = FString::Printf(TEXT("https://yfg5i8v0w4.execute-api.us-west-2.amazonaws.com/potato-api-test-stage"));
	LoginURI = FString::Printf(TEXT("/login"));
	StartSessionURI = FString::Printf(TEXT("/startsession"));
}

void UOfflineMainMenuWidget::OnLoginClicked()
{
	LoginRequest(user, pass);
}

void UOfflineMainMenuWidget::LoginRequest(FString usr, FString pwd)
{
	TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject());
	JsonObject->SetStringField(TEXT("username"), *FString::Printf(TEXT("%s"), *usr));
	JsonObject->SetStringField(TEXT("password"), *FString::Printf(TEXT("%s"), *pwd));

	// stick it into JsonBody
	FString JsonBody;
	TSharedRef<TJsonWriter<TCHAR>> JsonWriter = TJsonWriterFactory<>::Create(&JsonBody);
	FJsonSerializer::Serialize(JsonObject.ToSharedRef(), JsonWriter);

	// make http request
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> LoginHttpRequest = Http->CreateRequest();
	LoginHttpRequest->SetVerb("POST");
	LoginHttpRequest->SetURL(ApiGatewayEndpoint + LoginURI);
	LoginHttpRequest->SetHeader("Content-Type", "application/json");
	LoginHttpRequest->SetContentAsString(JsonBody);
	LoginHttpRequest->OnProcessRequestComplete().BindUObject(this, &UOfflineMainMenuWidget::OnLoginResponse);
	LoginHttpRequest->ProcessRequest();

}

void UOfflineMainMenuWidget::OnLoginResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful)
{
	if (bWasSuccessful)
	{
		TSharedPtr<FJsonObject> JsonObject;
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Response->GetContentAsString());
		if (FJsonSerializer::Deserialize(Reader, JsonObject))
		{
			FString IdToken = JsonObject->GetObjectField("tokens")->GetStringField("IdToken");
			StartSessionRequest(IdToken);
		}
	}

}
void UOfflineMainMenuWidget::StartSessionRequest(FString idt)
{
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> StartSessionHttpRequest = Http->CreateRequest();
	StartSessionHttpRequest->SetVerb("GET");
	StartSessionHttpRequest->SetURL(ApiGatewayEndpoint + StartSessionURI);
	StartSessionHttpRequest->SetHeader("Content-Type", "application/json");
	StartSessionHttpRequest->SetHeader("Authorization", idt);
	StartSessionHttpRequest->OnProcessRequestComplete().BindUObject(this, &UOfflineMainMenuWidget::OnStartSessionResponse);
	StartSessionHttpRequest->ProcessRequest();

}
void UOfflineMainMenuWidget::OnStartSessionResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful)
{
	if (bWasSuccessful)
	{
		TSharedPtr<FJsonObject> JsonObject;
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Response->GetContentAsString());

		if (FJsonSerializer::Deserialize(Reader, JsonObject))
		{
			FString IpAddress = JsonObject->GetObjectField("PlayerSession")->GetStringField("IpAddress");
			FString Port = JsonObject->GetObjectField("PlayerSession")->GetStringField("Port");

			FString LevelName = IpAddress + ":" + Port;

			// the main goal
			UGameplayStatics::OpenLevel(GetWorld(), FName(*LevelName), false);
		}
	}
}
