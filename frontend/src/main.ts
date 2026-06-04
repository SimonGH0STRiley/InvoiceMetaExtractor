import { registerLocaleData } from "@angular/common";
import zh from "@angular/common/locales/zh";
import { provideHttpClient } from "@angular/common/http";
import { enableProdMode } from "@angular/core";
import {
  CaretLeftOutline,
  CaretRightOutline,
  CheckCircleOutline,
  CloseOutline,
  ClearOutline,
  DeleteOutline,
  EditOutline,
  ExportOutline,
  FilterOutline,
  FundOutline,
  ImportOutline,
  InfoCircleOutline,
  LeftOutline,
  LoadingOutline,
  MinusCircleOutline,
  PlusCircleOutline,
  RightOutline,
  SaveOutline,
  SearchOutline,
  SecurityScanOutline,
  SettingOutline,
  TransactionOutline,
} from "@ant-design/icons-angular/icons";
import { bootstrapApplication } from "@angular/platform-browser";
import { provideNzIcons } from "ng-zorro-antd/icon";
import { NZ_I18N, zh_CN } from "ng-zorro-antd/i18n";

import { AppComponent } from "./app/app.component";

registerLocaleData(zh);

if (location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
  enableProdMode();
}

bootstrapApplication(AppComponent, {
  providers: [
    provideHttpClient(),
    provideNzIcons([
      CaretLeftOutline,
      CaretRightOutline,
      CheckCircleOutline,
      CloseOutline,
      ClearOutline,
      DeleteOutline,
      EditOutline,
      ExportOutline,
      FilterOutline,
      FundOutline,
      ImportOutline,
      InfoCircleOutline,
      LeftOutline,
      LoadingOutline,
      MinusCircleOutline,
      PlusCircleOutline,
      RightOutline,
      SaveOutline,
      SearchOutline,
      SecurityScanOutline,
      SettingOutline,
      TransactionOutline,
    ]),
    { provide: NZ_I18N, useValue: zh_CN },
  ],
}).catch((err) => console.error(err));
